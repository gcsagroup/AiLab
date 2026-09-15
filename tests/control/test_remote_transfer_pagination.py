"""分页先按执行目标过滤，旧目标历史不会被其他目标的最近百条遮住。"""

from test_control import rig, post


def test_transfer_history_pages_and_cursor_are_scoped_to_target(rig):
    client, service, *_ = rig
    project = post(client, '/projects', {'name': '传输历史分页'})
    targets = [post(client, '/execution-targets', {'project_id': project['id'], 'name': name, 'origin': 'http://127.0.0.1:12345',
                    'executor_id': 'executor-' + 'a' * 32, 'credential_token': 'S' * 40}, 'target-' + str(index)) for index, name in enumerate(('较早目标', '最近目标'))]
    rows = []
    with service.store.transaction():
        for target in [targets[0], *([targets[1]] * 100)]:
            value = service.resource('attempt', project['id'], task_id='history-fixture', state='failed', state_version=1,
                                     compute_outcome='failed', collection_state='not_started', executor_type='remote',
                                     execution_target_id=target['id'], snapshot={'kind': 'text', 'operation': 'transfer'})
            service.store.put('attempt', value)
            rows.append(value)
    first = client.get('/api/v1/remote-transfers', params={'project_id': project['id']}).json()
    assert len(first['items']) == 100 and first['next_cursor']
    second = client.get('/api/v1/remote-transfers', params={'project_id': project['id'], 'cursor': first['next_cursor']}).json()
    assert [item['id'] for item in second['items']] == [rows[0]['id']] and second['next_cursor'] is None
    selected = client.get('/api/v1/remote-transfers', params={'project_id': project['id'], 'execution_target_id': targets[0]['id']}).json()
    assert [item['id'] for item in selected['items']] == [rows[0]['id']] and selected['next_cursor'] is None
    invalid = client.get('/api/v1/remote-transfers', params={'project_id': project['id'], 'execution_target_id': targets[0]['id'], 'cursor': first['next_cursor']})
    assert invalid.status_code == 400 and invalid.json()['error']['code'] == 'INVALID_CURSOR'

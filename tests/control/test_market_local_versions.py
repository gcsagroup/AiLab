"""真实临时库/回环小下载后离线发现；不启动App或模型，不接触既有库。"""
import copy
from unittest.mock import Mock

import pytest

from test_control import rig
from test_market import market, browse, download, task_context
from test_market_http import market_http, post
from fixture_market_provider import decide
from ailab_control.market import LoopbackProvider


def local(client, project_id, provider_id='fixture-provider'):
    return client.get('/api/v1/market/local-versions', params={'project_id': project_id, 'provider_id': provider_id})


def no_network(target, monkeypatch):
    spies = []
    for provider in target.providers.values():
        for method in ('json', 'open'):
            spy = Mock(side_effect=AssertionError('本地读取禁止提供方请求'))
            monkeypatch.setattr(provider, method, spy); spies.append(spy)
    return spies


def database_state(target):
    return target.store.db.total_changes, tuple(target.store.db.iterdump())


@pytest.mark.parametrize('dataset_key,kind', [('dialogue', 'text'), ('pictures', 'image')])
def test_completed_download_discovered_offline_registered_and_applied_exactly(market_http, monkeypatch, dataset_key, kind):
    client, target, project, provider = market_http
    task, context = task_context((target, project, provider), kind)
    version = browse((target, project, provider), dataset_key)
    completed = download((target, project, provider), version)
    assert completed['state'] == 'completed' and completed['complete']
    assert provider.ranges  # 真实回环传输，非完成状态桩。
    provider.shutdown(); provider.server_close()
    offline = client.get('/api/v1/market/catalog', params={'project_id': project['id'], 'provider_id':'fixture-provider'})
    assert offline.status_code == 503 and offline.json()['error']['code'] == 'MARKET_PROVIDER_UNAVAILABLE'
    spies = no_network(target, monkeypatch)
    before = database_state(target)
    found = local(client, project['id'])
    assert found.status_code == 200, found.text
    assert found.json() == {'versions':[version]}
    activity = client.get('/api/v1/market/versions/' + version['id'] + '/activity')
    assert activity.status_code == 200 and activity.json()['downloads'] == [completed]
    assert database_state(target) == before
    imported = post(client, '/market/downloads/' + completed['id'] + '/datasets', {}, 'offline-register')
    after_register = database_state(target)
    assert post(client, '/market/downloads/' + completed['id'] + '/datasets', {}, 'offline-register') == imported
    assert database_state(target) == after_register
    assert len(target.store.list('dataset', project['id'])) == 1
    assert local(client, project['id']).json() == {'versions':[version]}  # 登记后仍能发现。
    assert target.store.get('task', task['id']) == task
    applied = post(client, '/market/contexts/' + context['id'] + '/use', {'dataset_id':imported['id']}, 'offline-use')
    expected = copy.deepcopy(task['draft']); expected['dataset_id'] = imported['id']
    assert applied['task']['draft'] == expected
    assert applied['task']['draft_revision'] == task['draft_revision'] + 1
    assert {k:v for k,v in applied['task'].items() if k not in {'draft','draft_revision','updated_at'}} == {k:v for k,v in task.items() if k not in {'draft','draft_revision','updated_at'}}
    assert applied['return_to'] == {'project_id':project['id'],'task_id':task['id'],'kind':kind,'step':'data','highlight_dataset_id':imported['id']}
    assert applied['previous_checks_invalidated'] is True
    after_apply = database_state(target)
    assert post(client, '/market/contexts/' + context['id'] + '/use', {'dataset_id':imported['id']}, 'offline-use') == applied
    assert database_state(target) == after_apply and not target.store.list('attempt')
    for spy in spies: spy.assert_not_called()


def test_project_source_isolation_empty_and_complete_filter_order(market_http, monkeypatch):
    client, target, project, provider = market_http
    versions = target.browse(project['id'],'fixture-provider')['versions']
    assert local(client,project['id']).json() == {'versions':[]}  # 仅浏览不显示。
    picture = next(v for v in versions if v['metadata']['dataset_key']=='pictures')
    text = next(v for v in versions if v['metadata']['dataset_key']=='dialogue')
    download((target,project,provider),picture,'picture-first')
    download((target,project,provider),text,'text-second')
    download((target,project,provider),text,'text-repeat')
    pending = target.start_download(picture['id'],{'user_statement':'保留未完成'},'queued-extra')
    # 显式状态夹具只覆盖筛选组合；真实完整下载由上方实际传输提供。
    for state, flag in [('queued',False),('downloading',False),('failed',False),('cancelled',False),('completed',False),('failed',True)]:
        with target.store.transaction():
            row=target.store.get('market-download',pending['id']);row.update(state=state,complete=flag);target.store.put('market-download',row)
        found=local(client,project['id']);assert found.status_code==200,found.text
        assert found.json()=={'versions':[v for v in versions if v['id'] in {text['id'],picture['id']}]}
    other=target.service.project({'name':'另一个项目'})
    target.browse(other['id'],'fixture-provider')
    # 另一已登记来源没有自己的本地版本，不能混入同项目的原来源记录。
    target.providers['other-provider']=LoopbackProvider('other-provider',target.providers['fixture-provider'].origin)
    spies=no_network(target,monkeypatch);before=database_state(target)
    assert local(client,other['id']).json()=={'versions':[]}
    assert local(client,project['id'],'other-provider').json()=={'versions':[]}
    assert database_state(target)==before
    for spy in spies:spy.assert_not_called()


@pytest.mark.parametrize('state,complete',[('queued',False),('downloading',False),('failed',False),('cancelled',False),('completed',False),('failed',True)])
def test_only_complete_completed_downloads_qualify(market_http, state, complete):
    client,target,project,provider=market_http
    version=browse((target,project,provider))
    row=target.start_download(version['id'],{'user_statement':'筛选状态夹具'},'filter')
    with target.store.transaction():
        row.update(state=state,complete=complete);target.store.put('market-download',row)
    response=local(client,project['id'])
    assert response.status_code==200,response.text
    assert response.json()=={'versions':[]}


@pytest.mark.parametrize('damage,code,status',[('unknown','MARKET_SOURCE_NOT_ALLOWED',403),('origin','MARKET_SOURCE_CHANGED',409),('metadata','MARKET_VERSION_CHANGED',409),('project','RESOURCE_NOT_FOUND',404)])
def test_local_discovery_does_not_bypass_identity_or_hide_errors(market_http, monkeypatch, damage, code, status):
    client,target,project,provider=market_http
    version=browse((target,project,provider));download((target,project,provider),version)
    provider_id='fixture-provider';project_id=project['id']
    if damage=='unknown':provider_id='not-configured'
    elif damage=='origin':target.providers[provider_id]=LoopbackProvider(provider_id,'http://127.0.0.1:1')
    elif damage=='metadata':
        picture=browse((target,project,provider),'pictures')
        download((target,project,provider),picture,'valid-neighbor')
        with target.store.transaction():
            value=target.store.get('market-version',version['id']);value['metadata']['name']='改写已冻结元数据';target.store.put('market-version',value)
    else:project_id='project-does-not-exist'
    spies=no_network(target,monkeypatch);before=database_state(target)
    result=local(client,project_id,provider_id)
    assert result.status_code==status,result.text
    assert result.json()['error']['code']==code and database_state(target)==before
    for spy in spies:spy.assert_not_called()


def test_restricted_completed_history_is_not_refreshed_but_new_download_still_requires_provider(market_http, monkeypatch):
    client,target,project,provider=market_http
    version=browse((target,project,provider),'limited')
    access=target.request_access(version['id'],{'purpose':'离线完成记录测试','user_statement':'仅测试'},'request')
    decide(provider.state,access['provider_response']['request_id'],'approved','提供方明确允许')
    completed=download((target,project,provider),version,'approved',access['id'])
    assert completed['state']=='completed'
    provider.shutdown();provider.server_close()
    found=local(client,project['id']);assert found.status_code==200,found.text
    assert found.json()=={'versions':[version]}
    original=target.store.get('market-access',access['id'])
    with monkeypatch.context() as scoped:
        spies=no_network(target,scoped)
        imported=post(client,'/market/downloads/'+completed['id']+'/datasets',{},'restricted-offline-register')
        assert imported['market_provenance']['access_id']==access['id']
        assert target.store.get('market-access',access['id'])==original
        for spy in spies:spy.assert_not_called()
    previous=target.store.list('market-download')
    denied=client.post('/api/v1/market/downloads',json={'version_id':version['id'],'access_id':access['id'],'user_statement':'不能用历史审批跳过远端'},headers={'Idempotency-Key':'fresh-offline'})
    assert denied.status_code==503 and denied.json()['error']['code']=='MARKET_PROVIDER_UNAVAILABLE'
    assert target.store.list('market-download')==previous


def test_discovery_does_not_replace_registration_file_checks(market_http):
    client,target,project,provider=market_http
    version=browse((target,project,provider));completed=download((target,project,provider),version)
    file=target.root/completed['id']/'files'/version['metadata']['files'][0]['path']
    file.write_bytes(b'corrupt')
    found=local(client,project['id']);assert found.status_code==200,found.text
    assert found.json()=={'versions':[version]}  # 列表是持久完成记录，不是每次重验所有文件。
    response=client.post('/api/v1/market/downloads/'+completed['id']+'/datasets',json={},headers={'Idempotency-Key':'corrupt-register'})
    assert response.status_code==409 and response.json()['error']['code']=='ARTIFACT_CORRUPT'
    assert not target.store.list('dataset')

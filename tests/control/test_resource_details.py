"""分页之外按原编号补回任务引用；不创建资源或修改旧记录。"""
import pytest
from test_control import rig, post

@pytest.mark.parametrize('route,kind', [('projects','project'),('datasets','dataset'),('materials','material'),('evaluation-plans','evaluation-plan')])
def test_resource_detail_reads_original_record_and_rejects_wrong_kind(rig, route, kind):
    client,service,*_=rig
    project=post(client,'/projects',{'name':'原引用'})
    if kind=='project':
        resource=project
    else:
        with service.store.transaction():
            resource=service.resource(kind,project['id'],name='任务引用的后页资源')
            service.store.put(kind,resource)
    before=service.store.get(kind,resource['id'])
    response=client.get(f"/api/v1/{route}/{resource['id']}")
    assert response.status_code==200 and response.json()['id']==resource['id']
    assert service.store.get(kind,resource['id'])==before
    assert client.get(f'/api/v1/{route}/missing').status_code==404
    if kind!='project':
        assert client.get(f"/api/v1/{route}/{project['id']}").status_code==404

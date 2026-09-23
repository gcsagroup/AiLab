"""运行详情的作品保存标记必须来自当前项目、执行及真实产物登记。"""
import pytest
from test_control import rig, post

@pytest.mark.parametrize('kind', ['text', 'image', 'video', 'audio'])
def test_saved_work_status_is_scoped_and_does_not_write(rig, kind):
 client,service,_,_=rig
 project=post(client,'/projects',{'name':'当前项目'})
 other=post(client,'/projects',{'name':'其他项目'})
 attempt=service.resource('attempt',project['id'],state='succeeded',state_version=1,compute_outcome='succeeded',collection_state='succeeded',snapshot={'kind':kind,'operation':'generate'})
 artifact=service.resource('artifact',project['id'],attempt_id=attempt['id'],relative_path='result.txt',media_type='text/plain')
 with service.store.transaction():
  service.store.put('attempt',attempt);service.store.put('artifact',artifact)
  for bank,run,body in [(project['id'],'other-attempt',artifact['id']),(other['id'],attempt['id'],artifact['id']),(project['id'],attempt['id'],'missing-artifact')]:
   item=service.resource('work',bank,attempt_id=run,artifact_id=body);service.store.put('work',item)
 before=service.store.db.total_changes
 assert client.get('/api/v1/attempts/'+attempt['id']).json()['saved_work_artifact_ids']==[]
 assert service.store.db.total_changes==before
 with service.store.transaction():
  item=service.resource('work',project['id'],attempt_id=attempt['id'],artifact_id=artifact['id']);service.store.put('work',item)
 before=service.store.db.total_changes
 assert client.get('/api/v1/attempts/'+attempt['id']).json()['saved_work_artifact_ids']==[artifact['id']]
 assert service.store.db.total_changes==before

"""7B 控制入口及来源组门禁；HTTP夹具不替代真实模型执行。"""
import json
import pytest
from test_control import rig, make_model, post
from dataset_split_fixtures import setup_split, prepare_split, TEMPLATE

LARGE = {'model_type':'qwen2','hidden_size':3584,'num_hidden_layers':28,'num_attention_heads':28,'num_key_value_heads':4,'intermediate_size':18944,'vocab_size':152064,'tie_word_embeddings':False}


def import_large(rig, project, config):
    client, _, source, _ = rig
    path = make_model(source / ('large-' + project['id']))
    (path / 'config.json').write_text(json.dumps(config))
    (path / 'tokenizer_config.json').write_text(json.dumps({'chat_template': TEMPLATE}))
    for name in ('tokenizer.json', 'vocab.json', 'merges.txt'):
        (path / name).write_text(json.dumps({'fixture_only': name}))
    plan = post(client, '/models/import-plans', {'project_id':project['id'],'path':str(path)})
    return post(client, '/models/imports', {'plan_id':plan['id'],'manifest_digest':plan['manifest_digest']}, 'import-large')


@pytest.mark.parametrize('changed,blocked', [({},False),({'num_key_value_heads':2},True),({'quantization':{'bits':4,'group_size':64,'mode':'affine'}},True)])
def test_large_generation_uses_same_profile_as_worker(rig, changed, blocked):
    client=rig[0];project=post(client,'/projects',{'name':'大模型合同'})
    model=import_large(rig,project,{**LARGE,**changed})
    task=post(client,'/tasks',{'project_id':project['id'],'kind':'text','operation':'generate','name':'合同'})
    task['draft'].update(model_id=model['id'],input={'prompt':'仅合同检查'})
    task=client.patch('/api/v1/tasks/'+task['id']+'/draft',json={'expected_revision':1,'draft':task['draft']}).json()
    result=post(client,'/tasks/'+task['id']+'/preflight',{'draft_revision':task['draft_revision']})
    assert any(e['code']=='MODEL_UNVERIFIED' for e in result['blocking']) == blocked
    if not blocked: assert result['can_submit']


def test_large_source_group_preparation_reaches_cpu_checker(rig, monkeypatch):
    values=setup_split(rig,monkeypatch,apply=False)
    model=import_large(rig,values['project'],LARGE)
    plan,_=prepare_split(rig[0],values['project'],model,values['source'],key='large-split')
    assert plan['status']=='ready', plan
    assert plan['counts']['accepted_samples']==4


def test_control_model_profiles_match_worker_contract():
    """控制服务必须能独立安装；模型边界与执行器保持一致。"""
    from adapters.mlx_text.profiles import model_profile as worker_profile
    from ailab_control.model_profiles import model_profile as control_profile
    import inspect

    assert inspect.getsource(control_profile) == inspect.getsource(worker_profile)

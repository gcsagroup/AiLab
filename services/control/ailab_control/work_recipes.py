"""作品原配方只读与普通草稿复用；收藏独立于生成和人工修订。"""

import copy

from pydantic import ValidationError

from .storage import Fault, digest


class WorkRecipes:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def work(self, work_id, project_id):
        work = self.store.get('work', work_id)
        if work['project_id'] != project_id:
            raise Fault('PROJECT_MISMATCH', '作品属于其他项目，请返回所属项目操作。', 403)
        self.store.get('project', project_id)
        return work

    def source(self, work_id, project_id):
        self.work(work_id, project_id)
        try:
            return self.service.work_revisions.original_source(work_id)
        except Fault as error:
            if error.code == 'WORK_SOURCE_CHANGED':
                raise Fault(error.code, '作品原生成来源不完整或已变化，无法读取或复用配方。', error.status, **error.details) from error
            raise

    @staticmethod
    def lineage(source):
        return {'source_work_id': source['work']['id'], 'source_attempt_id': source['attempt']['id'],
                'source_recipe_digest': digest(source['work']['recipe'])}

    def view(self, work_id, project_id):
        with self.store.lock:
            source = self.source(work_id, project_id)
            return {'work': self.service.public(source['work']), 'recipe': copy.deepcopy(source['work']['recipe']),
                    **self.lineage(source)}

    def reference(self, kind, resource_id, project_id, field):
        if not resource_id:
            raise Fault('WORK_RECIPE_REFERENCE_MISSING', '原配方缺少必要资源，不能创建复用草稿。', 409, field=field)
        try:
            resource = self.store.get(kind, resource_id)
        except Fault as error:
            if error.code == 'RESOURCE_NOT_FOUND':
                raise Fault('WORK_RECIPE_REFERENCE_MISSING', '原配方引用的资源已不存在，不能创建复用草稿。', 409, field=field, resource_id=resource_id) from error
            raise
        if resource['project_id'] != project_id:
            raise Fault('PROJECT_MISMATCH', '原配方资源属于其他项目，不能创建复用草稿。', 403, field=field)
        return resource

    @staticmethod
    def version(resource, recipe, version_field, digest_field, field):
        if not recipe.get(version_field) or not recipe.get(digest_field) or resource.get('version_id') != recipe[version_field] or resource.get('manifest_digest') != recipe[digest_field]:
            raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原配方资源的版本或内容身份已变化，不能创建复用草稿。', 409, field=field, resource_id=resource['id'])

    def draft(self, recipe, project_id):
        # 与普通草稿共用严格合同；只投影生成输入，封存快照和人工修订不进入草稿。
        from .api import Draft
        projected = {field: copy.deepcopy(recipe.get(field)) for field in ('model_id', 'adapter_id', 'execution_target_id', 'input', 'runtime')}
        projected.update(kind=recipe.get('kind', 'text'), operation='generate')
        try:
            draft = Draft.model_validate(projected).model_dump()
        except ValidationError as error:
            raise Fault('WORK_RECIPE_INVALID', '原配方输入或运行参数不符合当前草稿合同，请查看配方后手动新建。', 409) from error
        model = self.reference('model', draft['model_id'], project_id, 'model_id')
        self.version(model, recipe, 'model_version_id', 'model_manifest_digest', 'model_id')
        if model.get('modality', 'text') != draft['kind']:
            raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原模型类别与作品配方不一致，不能创建复用草稿。', 409, field='model_id')
        if draft['adapter_id']:
            adapter = self.reference('adapter', draft['adapter_id'], project_id, 'adapter_id')
            self.version(adapter, recipe, 'adapter_version_id', 'adapter_manifest_digest', 'adapter_id')
            if adapter.get('base_model_id') != model['id'] or adapter.get('base_model_version_id') != model['version_id'] or adapter.get('base_manifest_digest') != model['manifest_digest']:
                raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原适配器的基座身份与原模型不一致，不能创建复用草稿。', 409, field='adapter_id')
            if recipe.get('adapter_training_recipe_digest') and adapter.get('training_recipe_digest') != recipe['adapter_training_recipe_digest']:
                raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原适配器的训练配方身份已变化，不能创建复用草稿。', 409, field='adapter_id')
        if draft['kind'] == 'video':
            material = self.reference('material', draft['input']['material_id'], project_id, 'input.material_id')
            self.version(material, recipe, 'material_version_id', 'input_image_manifest_digest', 'input.material_id')
            if material.get('kind') != 'image' or recipe.get('material_id') != material['id']:
                raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原视频素材身份与配方不一致，不能创建复用草稿。', 409, field='input.material_id')
        if draft['execution_target_id']:
            target = self.reference('execution-target', draft['execution_target_id'], project_id, 'execution_target_id')
            original = recipe.get('execution_target')
            fields = ('id', 'origin', 'executor_id', 'transport', 'validation_scope')
            if not isinstance(original, dict) or any(not original.get(field) or original.get(field) != target.get(field, 'loopback_http' if field == 'transport' else None) for field in fields):
                raise Fault('WORK_RECIPE_REFERENCE_CHANGED', '原执行目标的地址或执行器身份已变化，不能创建复用草稿。', 409, field='execution_target_id')
        elif recipe.get('execution_target'):
            raise Fault('WORK_RECIPE_INVALID', '原执行位置缺少目标编号，不能自动改成本机。', 409)
        return draft

    def reuse(self, work_id, payload, key):
        scope = 'work-recipe:reuse:' + work_id
        # 保持来源读取与新建之间无其他写入；来源检查内部使用自己的事务。
        with self.store.lock:
            with self.store.transaction():
                if previous := self.store.replay(scope, key, payload):
                    return previous
            source = self.source(work_id, payload['project_id'])
            with self.store.transaction():
                draft = self.draft(source['work']['recipe'], payload['project_id'])
                name = payload.get('name') or ((source['work'].get('name') or '作品') + ' · 配方复用')[:120]
                task = self.service.resource('task', payload['project_id'], name=name, kind=draft['kind'], operation='generate',
                                             draft_revision=1, draft=draft, **self.lineage(source))
                self.store.put('task', task)
                response = self.service.public(task)
                self.store.remember(scope, key, payload, response)
                return response

    def favorite(self, work_id, payload):
        with self.store.transaction():
            work = self.work(work_id, payload['project_id'])
            work['favorite'] = payload['favorite']
            self.store.put('work', work)
            return self.service.public(work)

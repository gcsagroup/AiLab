"""每个工作库的界面选择；只存固定枚举和资源编号。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .storage import Fault

ResourceId = Annotated[str, Field(min_length=1, max_length=100)]
RecentTaskKey = Literal["text:train", "text:generate", "image:train", "image:generate",
                        "video:train", "video:generate", "audio:train", "audio:generate"]


class UIFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectContext(UIFields):
    page: Literal["home", "models", "data", "lab", "assets"]
    kind: Literal["text", "image", "video", "audio"]
    module_tab: Literal["train", "generate", "history"]
    data_tab: Literal["local", "market"]
    task_id: ResourceId | None
    workflow_id: ResourceId | None
    recent_tasks: dict[RecentTaskKey, ResourceId] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def one_selected_object(self):
        if self.task_id is not None and self.workflow_id is not None:
            raise ValueError("任务和工作流不能同时选中。")
        return self


class UIContextPatch(UIFields):
    project_id: ResourceId
    context: ProjectContext


class UIContext(UIFields):
    project_id: ResourceId | None
    projects: dict[ResourceId, ProjectContext]


def empty_context():
    return {"project_id": None, "projects": {}}


def validate_context(value, resolve, *, allow_missing=False):
    """读取可忽略已删除对象；写入和备份必须核实全部引用。"""
    try:
        result = UIContext.model_validate(value).model_dump(exclude_unset=True)
    except ValidationError as error:
        raise Fault("UI_CONTEXT_INVALID", "已保存的界面选择结构无效，请检查工作库记录。", 409) from error
    if result["project_id"] is not None and result["project_id"] not in result["projects"]:
        raise Fault("UI_CONTEXT_INVALID", "当前项目缺少对应的界面选择。", 409)

    def lookup(kind, resource_id):
        try:
            record = resolve(kind, resource_id)
        except Fault as error:
            if error.code != "RESOURCE_NOT_FOUND":
                raise
            if allow_missing:
                return None
            raise Fault("UI_CONTEXT_REFERENCE_MISSING", "界面选择引用的对象已不存在。", 409) from error
        if not isinstance(record, dict) or record.get("id") != resource_id:
            raise Fault("UI_CONTEXT_INVALID", "界面选择引用的对象编号不一致。", 409)
        return record

    for project_id, context in list(result["projects"].items()):
        if lookup("project", project_id) is None:
            del result["projects"][project_id]
            if result["project_id"] == project_id:
                result["project_id"] = None
            continue
        for field, kind in (("task_id", "task"), ("workflow_id", "workflow-run")):
            if context[field] is None:
                continue
            record = lookup(kind, context[field])
            if record is None:
                context[field] = None
            elif record.get("project_id") != project_id:
                raise Fault("PROJECT_MISMATCH", "选中的任务或工作流必须属于当前项目。", 403)
        for selection, task_id in list(context.get("recent_tasks", {}).items()):
            record = lookup("task", task_id)
            if record is None:
                del context["recent_tasks"][selection]
                continue
            if record.get("project_id") != project_id:
                raise Fault("PROJECT_MISMATCH", "最近选择的任务必须属于当前项目。", 403)
            kind, operation = selection.split(":")
            if (record.get("kind"), record.get("operation")) != (kind, operation):
                raise Fault("UI_CONTEXT_TASK_MISMATCH", "最近选择的任务类别或操作与续做入口不一致。", 409)
            if record.get("workflow_ref") is not None:
                raise Fault("UI_CONTEXT_WORKFLOW_TASK", "工作流任务须从工作流继续，不能作为普通草稿续做。", 409)
            if record.get("immutable_draft") is True:
                raise Fault("UI_CONTEXT_FIXED_TASK", "固定任务不能作为普通草稿续做。", 409)
    return result

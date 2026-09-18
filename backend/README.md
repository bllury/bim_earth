# BIM IFC Converter Backend

独立 IFC → 3D Tiles 转换服务。前端默认通过 Vite 将 `/api` 代理到
`http://localhost:8000`。项目元数据使用 SQLite，模型文件使用 `data/projects/` 文件目录。

## 安装

```bash
cd bim-earth/backend

# 先确认 Python 位置
py -0p

# 使用 py 启动器创建虚拟环境；如果只有特定版本，可写为 py -3.12
py -3 -m venv .venv

# Windows PowerShell 激活，注意开头是 .\，不是 ..
.\.venv\Scripts\Activate.ps1

# 如果 PowerShell 提示脚本执行策略限制，先执行：
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

python -m pip install --upgrade pip

# 安装包含 IfcOpenShell 的完整依赖
pip install -r requirements.txt
```

## 启动

Windows PowerShell 使用 `$env:` 设置环境变量：

```bash
$env:IFC_CONVERTER_MODE = "ifcopenshell"
uvicorn app.main:app --reload --port 8000
```

## 转换模式

服务默认使用 IfcOpenShell 做真实 IFC 转换，依赖已包含在 `requirements.txt` 中。
如果未安装 `ifcopenshell`，转换任务会返回明确的失败状态，不会伪造成功。

`requirements-core.txt` 只包含 FastAPI、uvicorn 等运行依赖，供离线自测使用：
把 `IFC_CONVERTER_MODE` 设为 `mock` 时会生成一个测试立方体，仅验证 API 和
3D Tiles 加载链路，不代表真实 IFC 几何。

### 几何并发与线程数

几何三角化默认按机器能力自动选择线程数：优先读容器 CPU 配额（cgroup v2/v1），
再退到 CPU 亲和与 `os.cpu_count()`，上限默认 8（超过约 8 线程收益反转）。
构件数少于 200 的小模型直接单线程，省掉线程池开销。

可用环境变量覆盖：

```bash
$env:IFC_CONVERT_THREADS = "4"       # 强制线程数（优先级最高）
$env:IFC_CONVERT_MAX_THREADS = "12"  # 调整自适应上限
```

实测（本机 i9-13900HX、6.1MB / 1111 构件模型）：1 线程 45.9s → 8 线程 15.2s，
约 3.0× 提速；构件集合、顺序（guid 序列）与输出体积完全一致，峰值内存 317MB → 343MB。

## 接口摘要

```text
POST /api/ifc/convert
GET  /api/ifc/convert/{taskId}
GET  /api/ifc/recent
PUT  /api/ifc/projects/{projectId}/camera
GET  /api/ifc/models/{modelId}/elements/{ifcGuid}/properties
GET  /api/ifc/models/{modelId}/elements/{ifcGuid}/business
PUT  /api/ifc/models/{modelId}/elements/{ifcGuid}/business
GET  /api/ifc/revisions/{revisionId}/metadata.json
GET  /api/ifc/revisions/{revisionId}/tiles/{asset}
```

## 代码边界

- `app/main.py` 只负责应用组装、配置和路由注册。
- `app/api/ifc.py` 负责 IFC HTTP 接口和请求响应转换。
- `app/services/` 负责转换任务调度、IfcOpenShell/Mock 转换、SQLite 和 3D Tiles 文件生成。

前端的 IFC 转换轮询位于 `src/features/ifc/useIfcConversion.ts`；Cesium 模型加载和交互仍由前端负责。本阶段不引入数据库、用户系统或新的任务队列。

## 数据目录

默认生成在 `backend/data/`：

```text
data/
  bim.sqlite3
  projects/{project_id}/revisions/{revision_id}/
    source.ifc
    tiles/
    metadata.json
  temp/
```

`bim.sqlite3` 保存项目、版本、转换状态、路径、模型位置、相机 JSON 和构件运维字段；大文件不进入数据库。构件运维字段按 `modelId + ifcGuid` 存于 `element_business` 表，删除模型版本时一并清理。上述目录属于运行时产物，不应提交到版本库。

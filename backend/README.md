# BIM IFC Converter Backend

独立 IFC → 3D Tiles 转换服务。前端默认通过 Vite 将 `/api` 代理到
`http://localhost:8000`。项目元数据使用 SQLite，模型文件使用 `data/projects/` 文件目录。

## 环境要求

- Python 3.11（64 位）。后端代码需要 3.9+，而 `ifcopenshell` 0.8.x 只提供 3.9~3.14 的 wheel，**不要用 Python 3.8**。
- 能访问 PyPI（首次安装需要下载 ifcopenshell wheel）。
- Windows 安装 Python 时勾选 py launcher，`py -3.11 -V` 能输出 3.11.x 再继续。

## 安装

```bash
cd bim-earth/backend

# 先确认 Python 位置（需要 3.11；本机 py -3 指向 3.8，不能用）
py -0p

# 明确使用 3.11 创建虚拟环境
py -3.11 -m venv .venv

# Windows PowerShell 激活，注意开头是 .\，不是 ..
.\.venv\Scripts\Activate.ps1

# 如果 PowerShell 提示脚本执行策略限制，先执行：
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

python -m pip install --upgrade pip

# 安装包含 IfcOpenShell 的完整依赖
pip install -r requirements.txt
```

激活成功后提示符前会有 `(.venv)`，用 `python -V` 确认是 3.11.x 再继续。

本机（这台机器）没有注册 `py -3.11`，可以用已装好依赖的 conda 环境创建虚拟环境：

```bash
C:\ana\envs\bim-ifc\python.exe -m venv .venv
```

用 Python 3.8 启动后端会在导入 `app.main` 时失败（`TypeError: 'type' object is not subscriptable`），端口不会监听。

## 启动

Windows PowerShell 使用 `$env:` 设置环境变量：

```bash
$env:IFC_CONVERTER_MODE = "ifcopenshell"
uvicorn app.main:app --reload --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 和 `Application startup complete` 才算启动成功；首次启动会自动创建 `data/`。

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

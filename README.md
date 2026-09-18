# BIM Earth

Vue 3 + TypeScript + Cesium 的 BIM/IFC 可视化工作台。前端提供三维地球、模型上传与变换、构件树、拾取高亮、属性/运维/批注面板和内置控制台；后端负责 IFC → 3D Tiles 转换、文件持久化和模型资源接口。

## 功能一览

### 三维场景与定位

- Cesium 三维地球，底图使用高德影像瓦片。
- 点击地球选择放置位置，并显示经纬度、高度标记。
- 顶部坐标工具支持高德地名搜索（需要 `VITE_AMAP_KEY`）和经纬度直接定位，并飞行到目标位置。

### 模型管理（左侧工作台）

- 上传 GLB/GLTF（可一并选择 `.bin` 与贴图文件）并在浏览器本地加载。
- 上传 IFC 到后端转换为 3D Tiles，任务卡显示排队、转换、完成、失败状态和实时进度，完成后自动加载。
- 每个模型都可以调整放置经纬度、缩放比例和绕 Z 轴旋转，支持定位飞行和删除。
- 删除 IFC 模型会同时删除后端 revision（源文件、瓦片和数据库记录）。
- 刷新页面后自动恢复最近一次转换完成的 IFC 模型及其经纬度和 Cesium 相机；可用 localStorage 键 `bim-earth-allow-recent-restore` 关闭该行为。

### 构件树与选择

- 构件树按 项目 → 楼层 → 类别 → 构件 组织，支持展开、按节点隐藏/显示、单选和多选。
- 未选中构件透明度可调；隐藏的构件不参与拾取，因此可以点选被遮挡的构件。
- 地图拾取与构件树选择联动：高亮当前构件、闪烁提示、相机飞行定位。
- 选中信息牌显示二维引导线、多选构件切换、基础信息、材料信息和飞行距离倍率。
- IFC 属性面板显示模型 ID、IFC GUID、Express ID、构件类型、楼层、专业、材料以及完整 IfcPropertySet。

### 运维与批注

- 运维字段：安装日期、保质期、到期日期、上次/下次巡检日期、巡检周期、维护状态、责任单位、备注。
- 运维字段按 `modelId + ifcGuid` 写入后端 SQLite（浏览器 localStorage 仍保留即时副本）。
- 构件批注支持标题、内容、类型、状态和截止日期，目前保存在浏览器 localStorage。

### 面板与日志

- 底部控制台收集 `console.warn/error`、全局脚本错误、未处理的 Promise 拒绝和 Vue 组件异常，支持仅看错误、清空和自动滚动。
- 左侧模型栏、右侧构件树、底部控制台都可以折叠，展开状态写入 localStorage。

### 后端转换与持久化

- FastAPI + IfcOpenShell 将 IFC 几何转换为 3D Tiles（`tileset.json`、`*.b3dm`、`metadata.json`）。
- 几何三角化多线程执行，线程数按机器 CPU 能力自适应；可用 `IFC_CONVERT_THREADS` 强制线程数，或用 `IFC_CONVERT_MAX_THREADS` 调整上限。
- 转换过程分阶段上报进度，前端任务卡实时显示。
- SQLite 保存项目、模型版本、转换状态、模型经纬度、相机 JSON 和构件运维字段；IFC 源文件和瓦片保存在文件系统。
- 瓦片与 metadata 接口把路径限制在对应 revision 的 `tiles/` 目录内，避免路径穿越。
- 没有安装 IfcOpenShell 时可以使用 mock 转换器验证上传、任务和 3D Tiles 加载链路（不代表真实几何）。

## 环境要求

- Node.js 20 及以上（开发环境使用 Node 24）
- Python 3.11，且能安装 `ifcopenshell`
- 高德 Web 服务 Key（仅地名搜索需要，经纬度定位不依赖）

## 快速启动

前端：

```powershell
npm install
npm run dev
```

后端（Windows PowerShell）：

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:IFC_CONVERTER_MODE = "ifcopenshell"
uvicorn app.main:app --reload --port 8000
```

必须用 Python 3.11 创建虚拟环境。本机 `py -3` 指向 Python 3.8，用 3.8 启动时后端会在导入阶段直接报 `TypeError: 'type' object is not subscriptable`，端口不会监听，前端上传随即失败。

前端默认运行在 `http://localhost:3000`，Vite 将 `/api` 代理到后端 `http://localhost:8000`。

`requirements.txt` 已包含 `ifcopenshell`；`IFC_CONVERTER_MODE` 的默认值也是 `ifcopenshell`，上面显式设置是为了避免复用到旧环境变量。后端首次启动会自动创建 `backend/data/`。

如果本机没有注册 `py -3.11`，可以直接用已装好依赖的 conda 环境启动：

```powershell
cd backend
C:\ana\envs\bim-ifc\python.exe -m uvicorn app.main:app --reload --port 8000
```

前端配置：复制 `.env.example` 为 `.env.local`，按需填写 `VITE_AMAP_KEY`。

## 项目结构

```text
src/
  App.vue                         应用组装和跨组件状态
  components/
    EarthViewer.vue               Cesium Viewer、底图、点击拾取和放置标记
    CoordinatePanel.vue           地名搜索和经纬度定位
    ModelUploader.vue             模型上传/加载、变换、构件树和选择协调
    BimComponentTree.vue          构件树、显隐、单选/多选
    SelectionInfoPanel.vue        选中构件信息牌、引导线和飞行距离
    IfcInspectorPanel.vue         IFC 属性、运维字段和批注
    ConsolePanel.vue              底部日志面板
  features/
    ifc/useIfcConversion.ts       IFC 上传和转换轮询
    viewer/useModelPrimitives.ts  GLB/3D Tiles 资源生命周期
    viewer/useBimModelState.ts    前端模型状态
    viewer/selectionState.ts      跨组件选择与隐藏状态
    console/appConsole.ts         日志收集和全局错误捕获
    layout/useLayoutState.ts      面板布局状态持久化
  services/ifcApi.ts              后端接口客户端和数据类型
  lib/                            IFC 拾取与模型坐标变换

backend/app/
  main.py                         配置、服务组装和路由注册
  api/ifc.py                      IFC 上传、转换、资源、相机和构件接口
  schemas.py                      请求与响应模型
  services/ifc_converter.py       异步转换任务编排和进度上报
  services/ifcopenshell_converter.py  真实 IFC 几何转换
  services/mock_converter.py      本地 mock 转换
  services/gltf_utils.py          glTF/b3dm/tileset 生成工具
  services/persistence.py         SQLite 与文件目录管理

docs/ARCHITECTURE.md              分层、持久化和调用链说明
```

## 持久化目录

运行后端时会自动创建：

```text
backend/data/
  bim.sqlite3
  projects/
    {project_id}/
      revisions/
        {revision_id}/
          source.ifc
          metadata.json
          tiles/
            tileset.json
            *.b3dm
  temp/
```

SQLite 保存项目、模型版本、文件路径、转换状态、模型经纬度、相机 JSON 和构件运维字段；IFC 原文件与转换结果保存在文件系统，不进入 SQLite BLOB。`backend/data/` 是运行时数据，不应提交到 Git。

## 调用关系

1. 用户在 `ModelUploader.vue` 选择文件：GLB/GLTF 由浏览器本地加载，IFC 进入后端转换流程。
2. `useIfcConversion.start()` 调用 `services/ifcApi.ts` 的 `uploadIfcFile()`。
3. `POST /api/ifc/convert` 创建 project 和 revision，写入 `source.ifc`，返回任务 ID。
4. `ConverterService` 在线程池中调用 IfcOpenShell 转换器，把结果写入 revision 的 `tiles/`，并把进度上报到任务状态。
5. 前端每 2 秒轮询 `GET /api/ifc/convert/{taskId}`，更新任务卡进度。
6. 转换完成后，前端用 Cesium 加载 tileset，请求 `metadata.json` 构建构件树和拾取索引。
7. 地图拾取或构件树选择都会进入同一套高亮、飞行和属性加载逻辑，按需调用构件属性接口。
8. 相机变化通过 `PUT /api/ifc/projects/{projectId}/camera` 防抖 500ms 保存；运维字段通过 `PUT /api/ifc/models/{modelId}/elements/{ifcGuid}/business` 防抖同步。
9. 页面重新打开后，前端调用 `GET /api/ifc/recent`，恢复最近完成的模型、其经纬度和相机。

## 接口摘要

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/ifc/convert` | 上传 IFC，创建项目和版本，返回任务 ID |
| GET | `/api/ifc/convert/{taskId}` | 查询转换状态和进度 |
| GET | `/api/ifc/recent` | 获取最近完成模型及其相机 |
| DELETE | `/api/ifc/revisions/{revisionId}` | 删除模型版本及其源文件和瓦片 |
| PUT | `/api/ifc/projects/{projectId}/camera` | 保存 Cesium 相机 |
| GET | `/api/ifc/projects/{projectId}/camera` | 查询项目相机 |
| GET | `/api/ifc/models/{modelId}/elements/{ifcGuid}` | 获取 metadata 中的构件条目 |
| GET | `/api/ifc/models/{modelId}/elements/{ifcGuid}/properties` | 获取构件基础信息、材料、Property Set 和运维字段 |
| GET | `/api/ifc/models/{modelId}/elements/{ifcGuid}/business` | 获取构件运维字段 |
| PUT | `/api/ifc/models/{modelId}/elements/{ifcGuid}/business` | 保存构件运维字段 |
| GET | `/api/ifc/revisions/{revisionId}/metadata.json` | 获取构件元数据 |
| GET | `/api/ifc/revisions/{revisionId}/tiles/{asset}` | 获取 tileset、b3dm 等资源 |

## 当前边界

- GLB/GLTF 只在浏览器本地加载，没有服务端版本表，刷新后不会自动恢复。
- IFC 模型的经纬度、比例和旋转调整只在当前会话生效；上传时的经纬度、Cesium 相机和运维字段会持久化，刷新后按上传位置和保存的相机恢复。
- 构件批注和界面偏好（面板展开状态、飞行距离、未选透明度等）仍保存在浏览器 localStorage。
- 转换任务状态保存在后端进程内存中，没有引入外部任务队列，适合单实例开发环境。
- 尚未实现用户、权限和多租户隔离，接口默认面向本机开发。
- `mock` 模式只验证 API 和 3D Tiles 链路，不代表真实 IFC 几何。

## 开发与检查

```powershell
# 前端
npm run lint
npm run build

# 后端（在 backend 目录、已激活虚拟环境）
python -m compileall -q app
```

更多分层、持久化和调用链说明见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

# BIM Earth

Vue 3 + TypeScript + Cesium BIM/IFC 可视化项目。前端负责地图、模型交互、构件树、选择高亮和信息面板；后端负责 IFC 文件持久化、转换和模型资源接口。

## 快速启动

前端：

```powershell
npm install
npm run dev
```

后端（Windows PowerShell）：

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-core.txt
$env:IFC_CONVERTER_MODE = "mock"
uvicorn app.main:app --reload --port 8000
```

真实 IFC 转换还需要：

```powershell
pip install ifcopenshell
$env:IFC_CONVERTER_MODE = "ifcopenshell"
```

前端默认运行在 `http://localhost:3000`，Vite 将 `/api` 代理到后端 `http://localhost:8000`。

## 项目结构

```text
src/
  App.vue                         应用组合和跨组件状态
  components/
    EarthViewer.vue               Cesium Viewer、地图点击和生命周期
    ModelUploader.vue             模型上传、加载、构件树和选择协调器
    BimComponentTree.vue          IFC 构件树
    SelectionInfoPanel.vue        选中构件二维信息牌和引导线
    IfcInspectorPanel.vue         IFC 属性、业务字段和批注
  features/
    ifc/useIfcConversion.ts       IFC 上传和转换轮询
    viewer/useModelPrimitives.ts  GLB/3D Tiles 资源生命周期
    viewer/useBimModelState.ts    前端模型状态
  services/ifcApi.ts              后端接口客户端和数据类型
  lib/                            IFC 拾取与模型坐标变换

backend/app/
  main.py                         配置、服务组装和路由注册
  api/ifc.py                      IFC 上传、转换、资源、最近模型和相机接口
  services/ifc_converter.py       异步转换任务编排
  services/ifcopenshell_converter.py 真实 IFC 转换
  services/mock_converter.py      本地 mock 转换
  services/persistence.py         SQLite 元数据和文件目录管理
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
          tiles/
            tileset.json
            *.b3dm
          metadata.json
  temp/
```

SQLite 保存项目、模型版本、文件路径、转换状态、模型位置和相机 JSON；IFC 原文件与转换结果保存在文件系统，不进入 SQLite BLOB。`backend/data/` 是运行时数据，不应提交到 Git。

## 调用关系

1. 用户在 `ModelUploader.vue` 选择 IFC。
2. `useIfcConversion.start()` 调用 `services/ifcApi.ts` 的 `uploadIfcFile()`。
3. `POST /api/ifc/convert` 创建 project 和 revision，写入 `source.ifc`，返回任务 ID。
4. `ConverterService` 在线程池中调用真实或 mock converter，把结果写入 revision 的 `tiles/`。
5. 前端轮询 `GET /api/ifc/convert/{taskId}`。
6. 转换完成后，`ModelUploader` 使用 Cesium 加载 tileset，并请求 `metadata.json` 构建构件树。
7. 相机变化通过 `PUT /api/ifc/projects/{project_id}/camera` 防抖保存。
8. 页面重新打开后，前端调用 `GET /api/ifc/recent`，恢复最近完成的模型、其地理位置和相机。

## 精简接口说明

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/ifc/convert` | 上传 IFC，创建转换任务 |
| GET | `/api/ifc/convert/{taskId}` | 查询转换状态 |
| GET | `/api/ifc/recent` | 获取最近完成模型及相机 |
| PUT | `/api/ifc/projects/{projectId}/camera` | 保存 Cesium 相机 |
| GET | `/api/ifc/projects/{projectId}/camera` | 查询项目相机 |
| GET | `/api/ifc/revisions/{revisionId}/metadata.json` | 获取构件元数据 |
| GET | `/api/ifc/revisions/{revisionId}/tiles/{asset}` | 获取 tileset、b3dm 等资源 |
| GET | `/api/ifc/models/{modelId}/elements/{ifcGuid}/properties` | 获取构件属性 |

## 当前边界

- GLB/GLTF 仍是浏览器本地加载，尚未建立其服务端文件版本表。
- 批注、业务字段和飞行距离目前仍使用浏览器 localStorage；模型文件、转换结果和 Cesium 相机已经进入后端持久层。
- `mock` 模式只验证 API 和 3D Tiles 链路，不代表真实 IFC 几何。
- UI 重构应优先修改 `src/components/` 和样式，避免改变 `services/`、`features/ifc/` 与后端接口契约。

更多设计说明见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

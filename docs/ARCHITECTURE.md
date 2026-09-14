# BIM Earth 架构与持久层说明

## 1. 分层

### 前端展示层

`App.vue` 只负责组装 `EarthViewer`、`CoordinatePanel` 和 `ModelUploader`，保存跨组件的 Viewer、位置和当前拾取构件。

`EarthViewer.vue` 创建 Cesium Viewer，负责：

- 初始化底图和场景；
- 处理地图点击；
- 将 IFC 构件拾取结果发送给父组件；
- 销毁 Viewer 和事件处理器。

### 前端业务协调层

`ModelUploader.vue` 是当前模型业务协调器，负责：

- 文件类型判断；
- GLB 本地加载；
- IFC 转换启动和轮询结果接收；
- 3D Tiles 加载；
- metadata 加载和构件树生成；
- 单选、多选、颜色闪烁、飞行定位；
- 右侧信息牌和 IFC 属性面板。

后续 UI 重构建议将它逐步拆为上传面板、模型列表、选择控制器和持久化 composable，但应保持现有 API 类型不变。

### 后端接口层

`backend/app/api/ifc.py` 只处理 HTTP 输入输出和路径安全校验。它不执行 IFC 几何解析。

### 后端服务层

- `ConverterService`：维护进程内转换任务状态，并在线程池中运行 converter；
- `IfcOpenShellConverter`：真实 IFC 几何与 metadata 转换；
- `MockConverter`：生成测试立方体；
- `PersistenceStore`：初始化 SQLite、创建 project/revision、保存状态和相机。

## 2. 持久化模型

### projects

保存项目身份和当前版本：

- `id`
- `name`
- `current_revision_id`
- `created_at`
- `updated_at`

### model_revisions

保存一次 IFC 上传及转换结果：

- `id`
- `project_id`
- `file_name`
- `source_path`
- `tiles_path`
- `metadata_path`
- `model_id`
- `status`
- `error`
- `longitude`
- `latitude`
- `height`
- `created_at`
- `updated_at`

### camera_states

按项目保存 Cesium 相机：

- `project_id`
- `camera_json`
- `updated_at`

相机 JSON 包含 `position`、`direction` 和 `up` 三个笛卡尔向量。页面恢复时使用 `Camera.setView()`，不保存 Cesium 对象本身。

## 3. 文件生命周期

上传时：

1. `PersistenceStore.create_revision()` 生成 project/revision ID；
2. 创建 `backend/data/projects/{project_id}/revisions/{revision_id}/`；
3. 上传流写入 `source.ifc`；
4. 转换器输出写入 `tiles/`；
5. `metadata.json` 写入 revision 根目录；
6. 转换成功后 SQLite 状态变为 `completed`。

转换失败时，SQLite 保存 `failed` 和错误消息，原始 IFC 保留，便于排查或重试策略后续扩展。

资源接口不会暴露任意文件路径，而是把请求路径限制在对应 revision 的 `tiles/` 目录内，防止 `../` 路径穿越。

## 4. 页面恢复流程

```text
页面加载
  -> Cesium Viewer ready
  -> GET /api/ifc/recent
  -> 得到最近 completed revision
  -> 加载 tileset URL
  -> 加载 metadata URL
  -> 注册构件树和拾取索引
  -> 恢复模型经纬度
  -> 恢复 camera JSON
```

如果数据库为空、模型文件已经被删除或资源接口返回错误，页面不会伪造成功状态；前端记录警告并保持地图可用。

## 5. 模型选择调用链

```text
地图点击
  -> EarthViewer.pickIfcFeature()
  -> App.handleIfcFeaturePicked()
  -> ModelUploader.handlePickedFeature()
  -> 更新 selectionOrder / activeGuideFeatureKey
  -> 更新 feature.color
  -> SelectionInfoPanel 投影引导线
  -> fetchIfcElementProperties()
```

构件树点击会绕过地图拾取，但最终进入相同的选择、高亮、飞行和属性加载逻辑。

## 6. 相机保存调用链

```text
Cesium camera.changed
  -> ModelUploader 防抖 500ms
  -> getCameraState()
  -> PUT /api/ifc/projects/{projectId}/camera
  -> camera_states upsert
```

相机保存失败只记录警告，不阻塞模型交互。相机恢复失败也不会阻止 tileset 加载。

## 7. 开发与验证

```powershell
npm run lint
npm run build

cd backend
.\.venv\Scripts\python.exe -m compileall -q app
```

建议验证：

- 空 IFC 和非法 IFC；
- mock 转换和真实转换；
- 页面刷新后恢复最近模型；
- 删除或移动 `backend/data/projects` 下资源后的错误表现；
- 相机旋转、缩放、平移后的重新打开恢复；
- 多选构件与引导线仍然正常；
- 路径穿越请求不能读取 tiles 目录外文件。

# LiDAR 房间建模 App（iOS）

用 iPhone / iPad 的激光雷达（LiDAR）扫描房间，生成两种模型：

| 模式 | 来源 | 得到什么 | 导出 |
|---|---|---|---|
| 贴图模式 | [RTAB-Map](https://github.com/introlab/rtabmap) 的 iOS App（BSD-3） | 带真实颜色贴图的网格，长得和房间一样 | OBJ、PLY |
| 户型模式 | 苹果 RoomPlan，代码参考 [iOS-RoomPlan](https://github.com/Furtado-Lyle/iOS-RoomPlan)（MIT） | 规整的墙、门、窗、家具，带尺寸 | USDZ、尺寸 JSON |

App 以 RTAB-Map 的 iOS App 为主体，在它的菜单里加入「户型扫描」。RTAB-Map 的工程依赖它整个仓库的 C++ 代码，所以 App 本身放在 RTAB-Map 的 fork 里；这个目录放我们自己写的户型模式代码和集成说明。

## 设备要求

- 有 LiDAR 的设备：iPhone 12 Pro 及之后的 Pro 机型，或 2020 年之后的 iPad Pro。
- iOS 17 或更高（户型模式用到 iOS 17 的 RoomPlan 接口）。
- 编译需要 Apple Silicon 的 Mac 和 Xcode 16。装到自己手机上用免费 Apple ID 即可；上架 App Store 需要付费开发者账号。

## 户型模式（`RoomPlanMode/Sources/`）

- `RoomCaptureContainer.swift`：把 RoomPlan 的扫描界面包成 SwiftUI 视图。
- `RoomMeasurements.swift`：从扫描结果算出地面面积、层高、墙总长，以及每面墙、门、窗、门洞、家具的尺寸（单位：米）。
- `RoomScanStore.swift`：每次扫描存成 `Documents/RoomPlan/<时间>/` 下的 `room.usdz`、`measurements.json`、`room.json`。
- `RoomPlanModeView.swift`：扫描列表、扫描界面、尺寸详情页（3D 预览、分享导出）。对外入口是 `RoomPlanMode.makeViewController()`。

## 集成到 RTAB-Map App

1. Fork `introlab/rtabmap`，在 Mac 上 clone 下来，按官方说明先编译依赖：

   ```sh
   cd rtabmap/app/ios/RTABMapApp
   ./install_deps.sh   # 第一次要编译 Boost、OpenCV、PCL、VTK 等，耗时较长
   ```

2. 把 `RoomPlanMode/Sources/` 里的 4 个文件拖进 Xcode 的 `RTABMapApp` target。
3. 把 target 的 iOS Deployment Target 改成 17.0。
4. 在 `ViewController.swift` 的文件菜单里加一项（放在 `New Mapping Session` 后面）。RoomPlan 和 RTAB-Map 不能同时占用摄像头，所以先暂停 RTAB-Map 的 ARSession（之后开始新的贴图扫描时，RTAB-Map 会在 `startCamera()` 里自己重新启动它）：

   ```swift
   if RoomPlanMode.isSupported {
       fileMenuChildren.append(UIAction(title: "户型扫描（RoomPlan）", image: UIImage(systemName: "square.split.bottomrightquarter"), attributes: actionNewScanEnabled ? [] : .disabled, handler: { _ in
           self.session.pause()
           self.present(RoomPlanMode.makeViewController(), animated: true)
       }))
   }
   ```

5. 连上手机，在 Xcode 里选中设备，点运行。

## 后续计划

- 两种模式共用同一次扫描：iOS 17 的 `RoomCaptureSession(arSession:)` 可以和 RTAB-Map 共用一个 ARSession，让户型模型和贴图模型在同一个坐标系里对齐叠加。
- 2D 户型图（PNG / PDF），可参考 [RoomPlanDemo](https://github.com/BaidetskyiYurii/RoomPlanDemo)，但它没写许可证，复用代码前要先问作者。

## 许可证注意

RTAB-Map 本身是 BSD-3，但它的依赖里有 GPL 组件（SuiteSparse 的 SPQR 等），而且编译时打开了 OpenCV 的 nonfree 模块（含专利算法）。自己使用没有问题；如果以后要上架收费，需要先把这些依赖换掉或关掉。

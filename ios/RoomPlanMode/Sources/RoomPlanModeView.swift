// 户型模式: scan a room with RoomPlan, keep a list of scans, show and share
// measurements and the USDZ model.

import SwiftUI
import RoomPlan
import QuickLook

/// Entry point for UIKit hosts such as RTAB-Map's ViewController:
/// `present(RoomPlanMode.makeViewController(), animated: true)`.
enum RoomPlanMode {
    static var isSupported: Bool { RoomCaptureSession.isSupported }

    static func makeViewController() -> UIViewController {
        let host = UIHostingController(rootView: RoomPlanModeView())
        host.modalPresentationStyle = .fullScreen
        return host
    }
}

struct RoomPlanModeView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var scans = RoomScanStore.all()
    @State private var isScanning = false
    @State private var path: [SavedRoomScan] = []

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if !RoomPlanMode.isSupported {
                    Text("这台设备没有激光雷达（LiDAR），不能用户型模式扫描。")
                        .foregroundStyle(.secondary)
                }
                ForEach(scans) { scan in
                    NavigationLink(value: scan) {
                        ScanRow(scan: scan)
                    }
                }
                .onDelete { offsets in
                    for index in offsets {
                        try? RoomScanStore.delete(scans[index])
                    }
                    scans = RoomScanStore.all()
                }
            }
            .overlay {
                if scans.isEmpty && RoomPlanMode.isSupported {
                    ContentUnavailableView("还没有户型扫描", systemImage: "cube.transparent",
                                           description: Text("点右上角开始扫描一个房间"))
                }
            }
            .navigationTitle("户型模式")
            .navigationDestination(for: SavedRoomScan.self) { scan in
                RoomResultView(scan: scan)
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("返回") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button("扫描", systemImage: "plus") { isScanning = true }
                        .disabled(!RoomPlanMode.isSupported)
                }
            }
            .fullScreenCover(isPresented: $isScanning) {
                RoomScanView { saved in
                    scans = RoomScanStore.all()
                    path = [saved]
                }
            }
        }
    }
}

private struct ScanRow: View {
    let scan: SavedRoomScan

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(scan.name).font(.headline)
            if let m = try? scan.loadMeasurements() {
                Text("面积 \(m.floorArea.squareMeters) · 层高 \(m.ceilingHeight.meters) · \(m.walls.count) 面墙")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

/// Full-screen RoomPlan capture. Calls `onSaved` after the scan is written to disk.
struct RoomScanView: View {
    @Environment(\.dismiss) private var dismiss
    var onSaved: (SavedRoomScan) -> Void

    @State private var controller = RoomCaptureController()
    @State private var isProcessing = false
    @State private var errorMessage: String?

    var body: some View {
        RoomCaptureContainer(
            controller: controller,
            onFinished: save,
            onError: { errorMessage = $0.localizedDescription }
        )
        .ignoresSafeArea()
        .overlay(alignment: .top) {
            HStack {
                Button("取消") { dismiss() }
                Spacer()
                Button(isProcessing ? "处理中…" : "完成") {
                    isProcessing = true
                    controller.finish()
                }
                .bold()
                .disabled(isProcessing)
            }
            .padding()
            .buttonStyle(.borderedProminent)
        }
        .alert("扫描失败", isPresented: .constant(errorMessage != nil)) {
            Button("好") { dismiss() }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func save(_ room: CapturedRoom) {
        do {
            let scan = try RoomScanStore.save(room, measurements: RoomMeasurements(room: room))
            onSaved(scan)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Measurements of one saved scan, with 3D preview and sharing.
struct RoomResultView: View {
    let scan: SavedRoomScan
    @State private var previewURL: URL?

    var body: some View {
        List {
            if let m = try? scan.loadMeasurements() {
                Section("房间") {
                    LabeledContent("地面面积", value: m.floorArea.squareMeters)
                    LabeledContent("层高", value: m.ceilingHeight.meters)
                    LabeledContent("墙总长", value: m.wallPerimeter.meters)
                }
                surfaceSection("墙（长 × 高）", m.walls)
                surfaceSection("门（宽 × 高）", m.doors)
                surfaceSection("窗（宽 × 高）", m.windows)
                surfaceSection("门洞（宽 × 高）", m.openings)
                if !m.objects.isEmpty {
                    Section("家具（宽 × 深 × 高）") {
                        ForEach(m.objects) { o in
                            LabeledContent(o.kind, value: "\(o.width.meters) × \(o.depth.meters) × \(o.height.meters)")
                        }
                    }
                }
            } else {
                Text("读不到这次扫描的尺寸数据。")
            }
        }
        .navigationTitle(scan.name)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button("3D 预览", systemImage: "cube") { previewURL = scan.modelURL }
                ShareLink("导出", items: [scan.modelURL, scan.measurementsURL])
            }
        }
        .quickLookPreview($previewURL)
    }

    @ViewBuilder
    private func surfaceSection(_ title: String, _ items: [RoomMeasurements.Surface]) -> some View {
        if !items.isEmpty {
            Section(title) {
                ForEach(Array(items.enumerated()), id: \.element.id) { index, s in
                    LabeledContent("\(s.kind) \(index + 1)", value: "\(s.width.meters) × \(s.height.meters)")
                }
            }
        }
    }
}

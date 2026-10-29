// Wraps RoomPlan's RoomCaptureView for SwiftUI.
// Pattern adapted from Furtado-Lyle/iOS-RoomPlan (MIT / CC0):
// https://github.com/Furtado-Lyle/iOS-RoomPlan

import SwiftUI
import RoomPlan

/// Lets the SwiftUI side ask the capture view to stop.
final class RoomCaptureController {
    fileprivate weak var captureView: RoomCaptureView?

    /// Stops scanning. RoomPlan then post-processes the data and calls `onFinished`.
    func finish() {
        captureView?.captureSession.stop()
    }
}

struct RoomCaptureContainer: UIViewRepresentable {
    let controller: RoomCaptureController
    var onFinished: (CapturedRoom) -> Void
    var onError: (Error) -> Void

    func makeUIView(context: Context) -> RoomCaptureView {
        let view = RoomCaptureView(frame: .zero)
        view.delegate = context.coordinator
        controller.captureView = view

        var configuration = RoomCaptureSession.Configuration()
        configuration.isCoachingEnabled = true
        view.captureSession.run(configuration: configuration)
        return view
    }

    func updateUIView(_ uiView: RoomCaptureView, context: Context) {}

    static func dismantleUIView(_ uiView: RoomCaptureView, coordinator: Coordinator) {
        uiView.captureSession.stop()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    // RoomCaptureViewDelegate inherits NSCoding, so the coordinator has to stub it.
    @objc(RoomPlanModeCaptureCoordinator)
    final class Coordinator: NSObject, RoomCaptureViewDelegate, NSCoding {
        let parent: RoomCaptureContainer

        init(parent: RoomCaptureContainer) {
            self.parent = parent
        }

        required init?(coder: NSCoder) { nil }
        func encode(with coder: NSCoder) {}

        func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
            true
        }

        func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
            if let error {
                parent.onError(error)
            } else {
                parent.onFinished(processedResult)
            }
        }
    }
}

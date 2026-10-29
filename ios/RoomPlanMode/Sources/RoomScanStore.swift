// Saves each RoomPlan scan as a folder in Documents/RoomPlan/:
//   room.usdz         parametric model (walls, doors, windows, furniture boxes)
//   measurements.json what RoomMeasurements extracted
//   room.json         RoomPlan's own CapturedRoom encoding, so the scan can be reloaded

import Foundation
import RoomPlan

struct SavedRoomScan: Identifiable, Hashable {
    let folder: URL
    var id: URL { folder }
    var name: String { folder.lastPathComponent }
    var modelURL: URL { folder.appendingPathComponent("room.usdz") }
    var measurementsURL: URL { folder.appendingPathComponent("measurements.json") }
    var roomURL: URL { folder.appendingPathComponent("room.json") }

    func loadMeasurements() throws -> RoomMeasurements {
        try RoomScanStore.decoder.decode(RoomMeasurements.self, from: Data(contentsOf: measurementsURL))
    }
}

enum RoomScanStore {
    static let root: URL = URL.documentsDirectory.appendingPathComponent("RoomPlan", isDirectory: true)

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    static func save(_ room: CapturedRoom, measurements: RoomMeasurements) throws -> SavedRoomScan {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH-mm-ss"
        let folder = root.appendingPathComponent(formatter.string(from: measurements.createdAt), isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

        let scan = SavedRoomScan(folder: folder)
        try room.export(to: scan.modelURL, exportOptions: .parametric)
        try encoder.encode(measurements).write(to: scan.measurementsURL)
        try encoder.encode(room).write(to: scan.roomURL)
        return scan
    }

    static func all() -> [SavedRoomScan] {
        let folders = (try? FileManager.default.contentsOfDirectory(
            at: root, includingPropertiesForKeys: nil, options: .skipsHiddenFiles
        )) ?? []
        return folders
            .map(SavedRoomScan.init)
            .filter { FileManager.default.fileExists(atPath: $0.measurementsURL.path) }
            .sorted { $0.name > $1.name }
    }

    static func delete(_ scan: SavedRoomScan) throws {
        try FileManager.default.removeItem(at: scan.folder)
    }
}

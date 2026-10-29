// Turns a RoomPlan CapturedRoom into plain, exportable measurements (meters).

import Foundation
import RoomPlan
import simd

struct RoomMeasurements: Codable {
    struct Surface: Codable, Identifiable {
        var id: UUID
        var kind: String
        var width: Float
        var height: Float
    }

    struct Object: Codable, Identifiable {
        var id: UUID
        var kind: String
        var width: Float
        var height: Float
        var depth: Float
    }

    var createdAt: Date
    var floorArea: Float
    var ceilingHeight: Float
    var wallPerimeter: Float
    var walls: [Surface]
    var doors: [Surface]
    var windows: [Surface]
    var openings: [Surface]
    var objects: [Object]
}

extension RoomMeasurements {
    init(room: CapturedRoom, createdAt: Date = .now) {
        self.createdAt = createdAt
        walls = room.walls.map { Surface($0, kind: "墙") }
        doors = room.doors.map { Surface($0, kind: "门") }
        windows = room.windows.map { Surface($0, kind: "窗") }
        openings = room.openings.map { Surface($0, kind: "门洞") }
        objects = room.objects.map(Object.init)
        ceilingHeight = room.walls.map(\.dimensions.y).max() ?? 0
        wallPerimeter = room.walls.map(\.dimensions.x).reduce(0, +)
        floorArea = room.floors.map(Self.area).reduce(0, +)
    }

    /// Area of a floor surface, from its outline when RoomPlan provides one.
    private static func area(of floor: CapturedRoom.Surface) -> Float {
        let corners = floor.polygonCorners
        guard corners.count >= 3 else {
            return floor.dimensions.x * max(floor.dimensions.y, floor.dimensions.z)
        }
        // Move the outline into world space, then use the shoelace formula on the
        // horizontal plane (ARKit is y-up).
        let points = corners.map { corner -> SIMD2<Float> in
            let world = floor.transform * SIMD4<Float>(corner, 1)
            return SIMD2(world.x, world.z)
        }
        var sum: Float = 0
        for i in points.indices {
            let a = points[i]
            let b = points[(i + 1) % points.count]
            sum += a.x * b.y - b.x * a.y
        }
        return abs(sum) / 2
    }
}

private extension RoomMeasurements.Surface {
    init(_ surface: CapturedRoom.Surface, kind: String) {
        self.init(id: surface.identifier, kind: kind, width: surface.dimensions.x, height: surface.dimensions.y)
    }
}

private extension RoomMeasurements.Object {
    init(_ object: CapturedRoom.Object) {
        self.init(
            id: object.identifier,
            kind: object.category.chineseName,
            width: object.dimensions.x,
            height: object.dimensions.y,
            depth: object.dimensions.z
        )
    }
}

extension CapturedRoom.Object.Category {
    var chineseName: String {
        switch self {
        case .storage: "柜子"
        case .refrigerator: "冰箱"
        case .stove: "灶台"
        case .bed: "床"
        case .sink: "水槽"
        case .washerDryer: "洗衣机"
        case .toilet: "马桶"
        case .bathtub: "浴缸"
        case .oven: "烤箱"
        case .dishwasher: "洗碗机"
        case .table: "桌子"
        case .sofa: "沙发"
        case .chair: "椅子"
        case .fireplace: "壁炉"
        case .television: "电视"
        case .stairs: "楼梯"
        @unknown default: "其他"
        }
    }
}

extension Float {
    /// "3.42 m"
    var meters: String { String(format: "%.2f m", self) }
    /// "12.3 m²"
    var squareMeters: String { String(format: "%.1f m²", self) }
}

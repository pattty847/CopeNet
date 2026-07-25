// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "CopeNetApple",
    platforms: [
        .macOS(.v14),
        .iOS(.v17),
    ],
    products: [
        .executable(name: "CopeNetApple", targets: ["CopeNetApple"]),
    ],
    targets: [
        .executableTarget(
            name: "CopeNetApple",
            path: "Sources"
        ),
    ]
)

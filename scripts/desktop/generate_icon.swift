import AppKit

// 使用几何图形生成应用图标，保持可重建，不依赖外部图片。
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
let background = NSBezierPath(roundedRect: NSRect(x: 32, y: 32, width: 960, height: 960), xRadius: 210, yRadius: 210)
NSColor(calibratedRed: 0.075, green: 0.12, blue: 0.23, alpha: 1).setFill()
background.fill()
let ring = NSBezierPath(ovalIn: NSRect(x: 185, y: 185, width: 654, height: 654))
ring.lineWidth = 26
NSColor(calibratedRed: 0.23, green: 0.80, blue: 0.71, alpha: 1).setStroke()
ring.stroke()
let text = "AI" as NSString
let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 285, weight: .bold),
    .foregroundColor: NSColor.white
]
let bounds = text.size(withAttributes: attributes)
text.draw(at: NSPoint(x: (1024 - bounds.width) / 2, y: (1024 - bounds.height) / 2 + 4), withAttributes: attributes)
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))

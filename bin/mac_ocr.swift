import Foundation
import Vision
import AppKit
import PDFKit

struct TextBlock: Codable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let confidence: Float
}

struct PageOCR: Codable {
    let file: String
    let page: Int
    let width: Double
    let height: Double
    let blocks: [TextBlock]
}

func performOCR(cgImage: CGImage, fileName: String, page: Int) -> PageOCR {
    var blocks: [TextBlock] = []
    let imgW = Double(cgImage.width)
    let imgH = Double(cgImage.height)
    
    let request = VNRecognizeTextRequest { req, _ in
        guard let observations = req.results as? [VNRecognizedTextObservation] else { return }
        for obs in observations {
            if let top = obs.topCandidates(1).first {
                let box = obs.boundingBox
                blocks.append(TextBlock(
                    text: top.string,
                    x: Double(box.origin.x),
                    y: Double(box.origin.y),
                    width: Double(box.size.width),
                    height: Double(box.size.height),
                    confidence: top.confidence
                ))
            }
        }
    }
    request.recognitionLanguages = ["zh-Hant", "zh-Hans", "en-US"]
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try? handler.perform([request])

    // Sort blocks by y descending (top to bottom), then x ascending (left to right)
    blocks.sort {
        if abs($0.y - $1.y) > 0.015 {
            return $0.y > $1.y
        }
        return $0.x < $1.x
    }
    return PageOCR(file: fileName, page: page, width: imgW, height: imgH, blocks: blocks)
}

func processPath(_ path: String) -> [PageOCR] {
    let url = URL(fileURLWithPath: path)
    let fileName = url.lastPathComponent
    var results: [PageOCR] = []

    if path.lowercased().hasSuffix(".pdf") {
        if let doc = PDFDocument(url: url) {
            for i in 0..<doc.pageCount {
                if let page = doc.page(at: i) {
                    let bounds = page.bounds(for: .cropBox)
                    let isRotated = page.rotation == 90 || page.rotation == 270
                    let width = isRotated ? bounds.height : bounds.width
                    let height = isRotated ? bounds.width : bounds.height
                    let scale: CGFloat = 2.0
                    let targetSize = NSSize(width: width * scale, height: height * scale)
                    let thumb = page.thumbnail(of: targetSize, for: .cropBox)
                    if let tiff = thumb.tiffRepresentation,
                       let rep = NSBitmapImageRep(data: tiff),
                       let cg = rep.cgImage {
                        results.append(performOCR(cgImage: cg, fileName: fileName, page: i + 1))
                    }
                }
            }
        }
    } else {
        if let image = NSImage(contentsOfFile: path),
           let tiff = image.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff),
           let cg = rep.cgImage {
            results.append(performOCR(cgImage: cg, fileName: fileName, page: 1))
        }
    }
    return results
}

var allResults: [PageOCR] = []
for arg in CommandLine.arguments.dropFirst() {
    allResults.append(contentsOf: processPath(arg))
}

let encoder = JSONEncoder()
encoder.outputFormatting = .prettyPrinted
if let data = try? encoder.encode(allResults), let str = String(data: data, encoding: .utf8) {
    print(str)
}

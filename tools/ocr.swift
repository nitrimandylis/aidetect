// OCR a page image with macOS Vision and print one line per recognised text run.
//
// Why Vision and not tesseract: it ships with the OS, needs no install, and on
// the 200 dpi grayscale scans in the IBO exemplar collection it returns 1.000
// confidence on body text. It is also the tool the first twelve human-tech
// samples were transcribed with, so the corpus stays internally consistent.
//
//   swiftc -O ocr.swift -o ocr
//   ./ocr page-01.png page-02.png > essay.tsv
//
// Output is TSV: text, x-origin, y-origin, width, confidence. The geometry is
// the point of it. Vision returns lines, not paragraphs, and the only reliable
// paragraph signal in a justified academic scan is the vertical gap: body lines
// step by ~0.029 of page height, a paragraph break by ~0.061. Indentation is
// useless here (0.1622 vs 0.1643 is noise). See build_corpus.py.
//
// Coordinates are Vision's: origin bottom-left, normalised 0..1.

import Foundation
import Vision
import AppKit

var status: Int32 = 0

for path in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOfFile: path),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("could not read \(path)\n".data(using: .utf8)!)
        status = 1
        continue
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.revision = VNRecognizeTextRequestRevision3

    do {
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    } catch {
        FileHandle.standardError.write("OCR failed on \(path): \(error)\n".data(using: .utf8)!)
        status = 1
        continue
    }

    for observation in (request.results ?? []) {
        guard let candidate = observation.topCandidates(1).first else { continue }
        // A tab inside recognised text would corrupt the TSV. Vision does not
        // emit tabs, but a stray one would silently shift every later column.
        let text = candidate.string.replacingOccurrences(of: "\t", with: " ")
        let box = observation.boundingBox
        print(String(format: "%@\t%.4f\t%.4f\t%.4f\t%.3f",
                     text, box.minX, box.minY, box.width, candidate.confidence))
    }
    // One page per block, so build_corpus.py can tell where a page ended and
    // decide whether a paragraph carries over the break.
    print("---PAGEBREAK---")
}

exit(status)

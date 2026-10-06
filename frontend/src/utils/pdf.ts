import type { PdfJs } from '@react-pdf-viewer/core';

/**
 * Document options for every PDF viewer.
 *
 * pdfjs-dist stays on 3.x because @react-pdf-viewer 3.12 (its last release)
 * only supports pdfjs-dist 2 and 3. pdfjs-dist before 4.2.67 can run code
 * from a crafted PDF font when eval is allowed; isEvalSupported: false turns
 * that code path off.
 */
export const safePdfParams = (options: PdfJs.GetDocumentParams): PdfJs.GetDocumentParams =>
  Object.assign({}, options, { isEvalSupported: false });

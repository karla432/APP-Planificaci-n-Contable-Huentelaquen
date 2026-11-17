// Convierte un HTML en PDF con Chromium (Playwright). Uso: node html_a_pdf.js entrada.html salida.pdf
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [entrada, salida] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(entrada), { waitUntil: 'load' });
  await p.pdf({
    path: salida, format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;color:#777;width:100%;text-align:center;font-family:Arial">Hacienda Huentelauquén · Planificación Contable · página <span class="pageNumber"></span> de <span class="totalPages"></span></div>',
    margin: { top: '18mm', bottom: '20mm', left: '16mm', right: '16mm' },
  });
  await b.close();
})();

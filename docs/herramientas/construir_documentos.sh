#!/usr/bin/env bash
# Genera los PDF y Word de la documentación (manual de usuario y documentación técnica).
# Requisitos: pandoc, Node.js con Playwright (Chromium) y, para el Word, nada más.
# Uso:  docs/herramientas/construir_documentos.sh [carpeta_de_salida]
set -euo pipefail
cd "$(dirname "$0")/../.."
SALIDA="${1:-docs/entregables}"
mkdir -p "$SALIDA"
construir() {  # $1 = markdown, $2 = nombre de salida sin extensión, $3 = carpeta de recursos
  local md="$1" nombre="$2" recursos="$3" html="$SALIDA/$2.html"
  pandoc "$md" -o "$html" --standalone --toc --toc-depth=2 --embed-resources --resource-path="$recursos" \
    --css docs/herramientas/documento.css --metadata pagetitle="$nombre" -f markdown+pipe_tables+implicit_figures
  pandoc "$md" -o "$SALIDA/$nombre.docx" --toc --toc-depth=2 --resource-path="$recursos" -f markdown+pipe_tables+implicit_figures
  NODE_PATH="$(npm root -g)" node docs/herramientas/html_a_pdf.js "$html" "$SALIDA/$nombre.pdf"
  rm -f "$html"
}
[ -f docs/manual_usuario/manual_de_usuario.md ] && construir docs/manual_usuario/manual_de_usuario.md "Manual_de_usuario_Planificacion_Contable" docs/manual_usuario
[ -f docs/documentacion_tecnica.md ] && construir docs/documentacion_tecnica.md "Documentacion_tecnica_Planificacion_Contable" docs
echo "Listo: $SALIDA"

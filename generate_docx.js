#!/usr/bin/env node
/**
 * Gerador de Descritivo Funcional Guardian PRO
 * Usa docx-js para produzir DOCX com layout fiel ao modelo Toledo
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, ImageRun, AlignmentType, HeadingLevel, PageBreak,
  WidthType, ShadingType, BorderStyle, VerticalAlign, PageNumber,
  TableOfContents, LevelFormat, ExternalHyperlink, TabStopType, TabStopPosition,
  HorizontalPositionAlign, HorizontalPositionRelativeFrom,
  VerticalPositionAlign, VerticalPositionRelativeFrom,
  TextWrappingType, TextWrappingSide,
  PageNumberElement
} = require('docx');
const fs = require('fs');
const path = require('path');

// ── Ler dados do stdin ─────────────────────────────────────────────────────
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => raw += chunk);
process.stdin.on('end', async () => {
  try {
    const data = JSON.parse(raw);
    const buf = await buildDoc(data);
    process.stdout.write(buf);
  } catch (e) {
    process.stderr.write('ERRO: ' + e.message + '\n' + e.stack + '\n');
    process.exit(1);
  }
});

// ── Cores Toledo ──────────────────────────────────────────────────────────
const C_AZUL_ESC  = '1A3A6B';
const C_AZUL_MED  = '2E75B6';
const C_AZUL_CLR  = 'DCE6F1';
const C_AZUL_ROW  = 'EBF3FB';
const C_BRANCO    = 'FFFFFF';

// ── Medidas (DXA: 1440 = 1 polegada = 2.54cm) ────────────────────────────
// A4: 21.59cm x 27.94cm
const PG_W    = 12242;  // 21.59cm
const PG_H    = 15842;  // 27.94cm
const MG_L    = 1080;   // 1.905cm
const MG_R    = 1080;   // 1.905cm
const MG_T    = 1440;   // 2.54cm
const MG_B    = 1440;   // 2.54cm
const MG_HDR  = 567;    // 1.0cm
const MG_FTR  = 567;    // 1.0cm
const CW      = PG_W - MG_L - MG_R;  // 10082 DXA ≈ 17.78cm

// ── Bordas azuis Toledo ───────────────────────────────────────────────────
const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: C_BRANCO };
const NO_BORDERS = { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER };

const BLUE_BOTTOM = (color = C_AZUL_ESC, size = 8) => ({
  bottom: { style: BorderStyle.SINGLE, size, color, space: 1 },
  top: NO_BORDER, left: NO_BORDER, right: NO_BORDER
});

// ── Helpers ───────────────────────────────────────────────────────────────
function cm2dxa(cm) { return Math.round(cm * 1440 / 2.54); }
function cm2emu(cm) { return Math.round(cm * 914400 / 2.54); }

function spacingPara(before = 0, after = 0) {
  return { before, after };
}

function pageProps() {
  return {
    page: {
      size: { width: PG_W, height: PG_H },
      margin: { top: MG_T, bottom: MG_B, left: MG_L, right: MG_R,
                header: MG_HDR, footer: MG_FTR }
    }
  };
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function blueHline(size = 8, color = C_AZUL_ESC) {
  return new Paragraph({
    border: BLUE_BOTTOM(color, size),
    spacing: spacingPara(0, 0)
  });
}

// ── Título de seção (linha azul inferior, sem fundo) ─────────────────────
function sectionTitle(text) {
  return new Paragraph({
    spacing: spacingPara(120, 80),
    border: BLUE_BOTTOM(C_AZUL_ESC, 8),
    children: [new TextRun({
      text,
      font: 'Arial Black', size: 26, bold: true, color: C_AZUL_ESC
    })]
  });
}

// ── H1 com fundo azul escuro ──────────────────────────────────────────────
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: spacingPara(200, 80),
    shading: { fill: C_AZUL_ESC, type: ShadingType.CLEAR },
    indent: { left: 120 },
    children: [new TextRun({
      text, font: 'Arial Black', size: 26, bold: true, color: C_BRANCO
    })]
  });
}

// ── H2 com fundo azul claro + linha inferior ──────────────────────────────
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: spacingPara(160, 60),
    shading: { fill: C_AZUL_CLR, type: ShadingType.CLEAR },
    border: BLUE_BOTTOM(C_AZUL_ESC, 6),
    children: [new TextRun({
      text, font: 'Arial Black', size: 24, bold: true, color: C_AZUL_ESC
    })]
  });
}

// ── H3 simples ────────────────────────────────────────────────────────────
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: spacingPara(120, 40),
    children: [new TextRun({
      text, font: 'Arial', size: 22, bold: true, color: C_AZUL_MED
    })]
  });
}

// ── Parágrafo normal ──────────────────────────────────────────────────────
function para(text, opts = {}) {
  return new Paragraph({
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.JUSTIFY,
    spacing: spacingPara(opts.before ?? 40, opts.after ?? 40),
    children: [new TextRun({
      text: text || '',
      font: opts.font || 'Arial',
      size: opts.size || 22,
      bold: opts.bold || false,
      italic: opts.italic || false,
      color: opts.color || '000000'
    })]
  });
}

function emptyPara(before = 80, after = 80) {
  return new Paragraph({ spacing: spacingPara(before, after), children: [] });
}

// ── Célula de tabela ──────────────────────────────────────────────────────
function tc(text, w, opts = {}) {
  const isHdr = opts.header || false;
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { fill: opts.fill || (isHdr ? C_AZUL_ESC : C_BRANCO), type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: opts.align || AlignmentType.LEFT,
      spacing: spacingPara(60, 60),
      children: [new TextRun({
        text: String(text || '\u2014'),
        font: 'Arial', size: opts.size || 20,
        bold: opts.bold !== undefined ? opts.bold : isHdr,
        color: isHdr ? C_BRANCO : (opts.color || '000000')
      })]
    })]
  });
}

// ── Tabela genérica com cabeçalho azul ───────────────────────────────────
function makeTable(headers, rows, colWidths) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  const hRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => tc(h, colWidths[i], { header: true }))
  });
  const dataRows = rows.map((row, ri) =>
    new TableRow({
      children: row.map((cell, ci) =>
        tc(cell, colWidths[ci], { fill: ri % 2 === 0 ? C_BRANCO : 'F4F6FB' })
      )
    })
  );
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [hRow, ...dataRows]
  });
}

// ── Tabela de informações (2 colunas: label azul + valor) ─────────────────
function infoTable(rows, labelW, valueW) {
  return new Table({
    width: { size: labelW + valueW, type: WidthType.DXA },
    columnWidths: [labelW, valueW],
    rows: rows.map((row, ri) => new TableRow({
      children: [
        tc(row[0], labelW, { fill: C_AZUL_CLR, bold: true, color: C_AZUL_ESC }),
        tc(row[1], valueW, { fill: ri % 2 === 0 ? C_BRANCO : 'F7FAFD' })
      ]
    }))
  });
}

// ── Imagem inline ─────────────────────────────────────────────────────────
function imgPara(b64str, wCm, caption = '', opts = {}) {
  if (!b64str) return null;
  try {
    const b64 = b64str.includes('base64,') ? b64str.split('base64,')[1] : b64str;
    const buf = Buffer.from(b64, 'base64');
    const ext = b64str.startsWith('data:image/jpeg') ? 'jpg' : 'png';
    const wEmu = cm2emu(wCm);
    // Calcular altura proporcional se não fornecida
    const hEmu = opts.hCm ? cm2emu(opts.hCm) : Math.round(wEmu * 0.56);
    const pars = [];
    pars.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: spacingPara(opts.before ?? 60, opts.after ?? 20),
      children: [new ImageRun({ data: buf, transformation: { width: Math.round(wEmu/9144), height: Math.round(hEmu/9144) }, type: ext })]
    }));
    if (caption) {
      pars.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: spacingPara(0, 60),
        children: [new TextRun({ text: caption, font: 'Arial', size: 18, italic: true, color: '666666' })]
      }));
    }
    return pars;
  } catch (e) {
    process.stderr.write(`Imagem falhou (${caption}): ${e.message}\n`);
    return null;
  }
}

// ── Lê dimensões reais de PNG ou JPEG ────────────────────────────────────
function getImageAspectRatio(buf, ext) {
  try {
    if (ext === 'png') {
      const w = buf.readUInt32BE(16);
      const h = buf.readUInt32BE(20);
      if (w > 0 && h > 0) return h / w;
    } else {
      // JPEG: percorre segmentos até encontrar SOF0-SOF3 / SOF5-SOF7 / SOF9-SOF11
      let i = 2;
      while (i + 4 < buf.length) {
        if (buf[i] !== 0xFF) break;
        const marker = buf[i + 1];
        const segLen = buf.readUInt16BE(i + 2);
        if (marker >= 0xC0 && marker <= 0xCF && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
          const h = buf.readUInt16BE(i + 5);
          const w = buf.readUInt16BE(i + 7);
          if (w > 0 && h > 0) return h / w;
        }
        i += 2 + segLen;
      }
    }
  } catch (e) {}
  return 0.5; // fallback: proporção 2:1
}

// ── Cabeçalho: logo cliente (esq) + logo PRIX (dir) ──────────────────────
function buildHeader(clientLogoB64, prixLogoB64) {
  const children = [];
  
  // Parágrafo com logo cliente à esquerda e PRIX à direita usando tab stop
  const runs = [];
  
  // Logo cliente (esquerda)
  if (clientLogoB64) {
    try {
      const b64 = clientLogoB64.includes('base64,') ? clientLogoB64.split('base64,')[1] : clientLogoB64;
      const buf = Buffer.from(b64, 'base64');
      const ext = clientLogoB64.startsWith('data:image/jpeg') ? 'jpg' : 'png';
      runs.push(new ImageRun({ data: buf, transformation: { width: 106, height: 40 }, type: ext }));
    } catch(e) {
      runs.push(new TextRun({ text: '(logo cliente)', font: 'Arial', size: 16, color: 'AAAAAA' }));
    }
  } else {
    runs.push(new TextRun({ text: '', font: 'Arial', size: 16 }));
  }

  // Tab para lado direito
  runs.push(new TextRun({ text: '\t' }));

  // Logo PRIX (direita)
  if (prixLogoB64) {
    try {
      const b64 = prixLogoB64.includes('base64,') ? prixLogoB64.split('base64,')[1] : prixLogoB64;
      const buf = Buffer.from(b64, 'base64');
      runs.push(new ImageRun({ data: buf, transformation: { width: 126, height: 53 }, type: 'png' }));
    } catch(e) {}
  }

  children.push(new Paragraph({
    spacing: spacingPara(0, 0),
    tabStops: [{ type: TabStopType.RIGHT, position: CW }],
    children: runs
  }));

  // Linha separadora azul
  children.push(blueHline(6, C_AZUL_ESC));

  return new Header({ children });
}

// ── Rodapé: nome doc (esq) | Pág X de Y (dir) ────────────────────────────
function buildFooter(docTitle) {
  return new Footer({
    children: [new Paragraph({
      border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'C0C8D8', space: 1 } },
      spacing: spacingPara(0, 0),
      tabStops: [{ type: TabStopType.RIGHT, position: CW }],
      children: [
        new TextRun({ text: (docTitle || '').slice(0, 65), font: 'Arial', size: 16, color: '666666' }),
        new TextRun({ text: '\t', font: 'Arial', size: 16 }),
        new TextRun({ text: 'Página ', font: 'Arial', size: 16, color: '666666' }),
        new TextRun({ children: [new PageNumberElement({})], font: 'Arial', size: 16, color: '666666' }),
      ]
    })]
  });
}

// ── Decodifica entidades HTML ─────────────────────────────────────────────
function decodeHtml(str) {
  return (str || '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ').replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(n))
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCharCode(parseInt(h,16)));
}

// ── Extrai runs com formatação inline (bold, italic) ──────────────────────
function parseInlineRuns(html, baseOpts = {}) {
  const runs = [];
  // Processar tags inline: <b>, <strong>, <i>, <em>, <u>
  const parts = html.split(/(<\/?(?:b|strong|i|em|u)[^>]*>)/gi);
  let bold = false, italic = false, underline = false;
  for (const part of parts) {
    if (/^<(b|strong)>/i.test(part)) { bold = true; continue; }
    if (/^<\/(b|strong)>/i.test(part)) { bold = false; continue; }
    if (/^<(i|em)>/i.test(part)) { italic = true; continue; }
    if (/^<\/(i|em)>/i.test(part)) { italic = false; continue; }
    if (/^<u>/i.test(part)) { underline = true; continue; }
    if (/^<\/u>/i.test(part)) { underline = false; continue; }
    // Strip any remaining tags
    const text = decodeHtml(part.replace(/<[^>]+>/g, ''));
    if (!text) continue;
    runs.push(new TextRun({
      text,
      font: baseOpts.font || 'Arial',
      size: baseOpts.size || 22,
      bold: bold || baseOpts.bold || false,
      italic: italic || baseOpts.italic || false,
      underline: underline ? {} : undefined,
      color: baseOpts.color || '000000'
    }));
  }
  return runs.length ? runs : [new TextRun({ text: decodeHtml(html.replace(/<[^>]+>/g, '')), ...baseOpts })];
}

// ── Parse tabela HTML → docx Table ───────────────────────────────────────
function parseHtmlTable(tableHtml) {
  // Extrair todas as linhas
  const rowMatches = [...tableHtml.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)];
  if (!rowMatches.length) return null;

  // Calcular número de colunas
  let maxCols = 0;
  const rowData = rowMatches.map(rm => {
    const cells = [...rm[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)];
    maxCols = Math.max(maxCols, cells.length);
    return { cells, isHeader: /<th/i.test(rm[1]) };
  });
  if (maxCols === 0) return null;

  const colW = Math.floor(CW / maxCols);
  const colWidths = Array(maxCols).fill(colW);
  colWidths[maxCols-1] = CW - colW * (maxCols - 1);

  const docxRows = rowData.map((row, ri) => {
    const isHdr = row.isHeader || ri === 0;
    while (row.cells.length < maxCols) row.cells.push({ 1: '' });
    const cells = row.cells.map((cm, ci) => {
      const cellHtml = (cm[1] || '').trim();
      const cellText = decodeHtml(cellHtml.replace(/<[^>]+>/g, ''));
      return new TableCell({
        width: { size: colWidths[ci], type: WidthType.DXA },
        shading: { fill: isHdr ? C_AZUL_ESC : (ri % 2 === 0 ? C_BRANCO : 'F4F6FB'), type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
          spacing: spacingPara(60, 60),
          children: [new TextRun({
            text: cellText || '\u2014',
            font: 'Arial', size: 20,
            bold: isHdr,
            color: isHdr ? C_BRANCO : '000000'
          })]
        })]
      });
    });
    return new TableRow({ tableHeader: isHdr, children: cells });
  });

  return new Table({
    width: { size: CW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: docxRows
  });
}

// ── HTML completo → array de elementos docx ───────────────────────────────
// imgs: objeto data.guardianImgs — usado para resolver <img data-gimg="chave">
function htmlToParas(html, imgs) {
  if (!html) return [];
  imgs = imgs || {};
  const paras = [];

  // ── Strip cabeçalhos MIME/MHT (quando htmlContent vem do builder .mht) ──
  // Extrai apenas o conteúdo entre <body> e </body>, ou tudo após os headers
  if (html.includes('MIME-Version:') || html.includes('Content-Type: multipart')) {
    const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    if (bodyMatch) {
      html = bodyMatch[1];
    } else {
      // Fallback: pular até a primeira tag HTML
      const htmlTagIdx = html.search(/<html[\s >]/i);
      if (htmlTagIdx >= 0) html = html.slice(htmlTagIdx);
    }
  }

  // Strip conteúdo antes do primeiro <h1> (remove capa duplicada + tabelas Informações/Histórico)
  const firstH1idx = html.search(/<h1[\s>]/i);
  if (firstH1idx > 0) html = html.slice(firstH1idx);

  // Remove script/style
  html = html.replace(/<script[\s\S]*?<\/script>/gi, '');
  html = html.replace(/<style[\s\S]*?<\/style>/gi, '');

  const result = [];

  // Processar tabelas primeiro (extrair e marcar posição)
  // Usar tokenização sequencial
  const tokens = [];
  let pos = 0;
  const tagRe = /<(\/?)(\w+)([^>]*)>/g;
  let lastEnd = 0;

  // Tokenizar o HTML em blocos de alto nível
  // Dividir por tags de bloco principais mantendo conteúdo interno
  const blockRe = /<(h[1-6]|p|ul|ol|li|table|div|hr|br)(\s[^>]*)?>[\s\S]*?<\/\1>|<(hr|br)[^>]*\/?>/gi;
  const seen = new Set();
  let lastIdx = 0;

  // Extrair tabelas inteiras antes de processar o resto
  const tableRe = /<table[\s\S]*?<\/table>/gi;
  const tables = [];
  let tMatch;
  let htmlWithPlaceholders = html;
  let tIdx = 0;
  while ((tMatch = tableRe.exec(html)) !== null) {
    const placeholder = `__TABLE_${tIdx}__`;
    tables.push({ placeholder, html: tMatch[0] });
    htmlWithPlaceholders = htmlWithPlaceholders.replace(tMatch[0], placeholder);
    tIdx++;
  }

  // Extrair <img data-gimg="chave"> — imagens Guardian inline por seção
  const dgimgRe = /<img[^>]+data-gimg="([^"]+)"[^>]*\/?>/gi;
  const dgimgs = [];
  let dgMatch;
  const htmlForGimg = htmlWithPlaceholders;
  while ((dgMatch = dgimgRe.exec(htmlForGimg)) !== null) {
    const key = dgMatch[1];
    const placeholder = `__GIMG_${dgimgs.length}__`;
    dgimgs.push({ placeholder, key });
    htmlWithPlaceholders = htmlWithPlaceholders.replace(dgMatch[0], placeholder);
  }

  // Extrair <div class="pbk"> — quebra de página explícita do builder
  htmlWithPlaceholders = htmlWithPlaceholders.replace(/<div[^>]+class="pbk"[^>]*>[\s\S]*?<\/div>/gi, '__PBK__');

  // Agora processar o HTML sem tabelas nem imagens guardian
  // Dividir em segmentos por tags de bloco
  const segments = htmlWithPlaceholders.split(/(<h[1-6][^>]*>[\s\S]*?<\/h[1-6]>|<p[^>]*>[\s\S]*?<\/p>|<ul[^>]*>[\s\S]*?<\/ul>|<ol[^>]*>[\s\S]*?<\/ol>|__TABLE_\d+__|__GIMG_\d+__|__PBK__)/gi).filter(s => s.trim());

  for (const seg of segments) {
    const s = seg.trim();
    if (!s) continue;

    // Quebra de página explícita (div.pbk do builder)
    if (s === '__PBK__') {
      result.push(pageBreak());
      continue;
    }

    // Tabela placeholder
    const tph = s.match(/^__TABLE_(\d+)__$/);
    if (tph) {
      const tbl = parseHtmlTable(tables[parseInt(tph[1])].html);
      if (tbl) { result.push(emptyPara(20,10)); result.push(tbl); result.push(emptyPara(20,20)); }
      continue;
    }

    // Imagem Guardian inline — <img data-gimg="chave">
    const gph = s.match(/^__GIMG_(\d+)__$/);
    if (gph) {
      const { key } = dgimgs[parseInt(gph[1])];
      if (imgs[key]) {
        try {
          // Largura padrão por tipo de imagem
          const IMG_WIDTHS = {
            tag_cartao:    10.0,  // TAG físico — menor, cabe em meia coluna
            tela_inspecao: 10.0,  // Tela mobile — mais estreita
            tela_login:    12.0,  // Tela login — média
            arq_solucao:   16.0,  // Arquitetura — ocupa quase a largura toda
          };
          const b64 = imgs[key];
          const ext = b64.startsWith('data:image/jpeg') ? 'jpg' : 'png';
          const buf = Buffer.from(b64.includes('base64,') ? b64.split('base64,')[1] : b64, 'base64');
          const ratio = getImageAspectRatio(buf, ext);
          const wCm  = IMG_WIDTHS[key] || 15.0;
          const hCm  = Math.min(wCm * ratio, 12.0);
          const pars = imgPara(b64, wCm, '', { before: 20, after: 30, hCm });
          if (pars) result.push(...pars);
        } catch(e) {
          process.stderr.write(`data-gimg "${key}" falhou: ${e.message}\n`);
        }
      }
      continue;
    }

    // H1
    const h1m = s.match(/^<h1[^>]*>([\s\S]*?)<\/h1>$/i);
    if (h1m) {
      const text = decodeHtml(h1m[1].replace(/<[^>]+>/g,''));
      if (text) result.push(h1(text));
      continue;
    }
    // H2
    const h2m = s.match(/^<h2[^>]*>([\s\S]*?)<\/h2>$/i);
    if (h2m) {
      const text = decodeHtml(h2m[1].replace(/<[^>]+>/g,''));
      if (text) result.push(h2(text));
      continue;
    }
    // H3
    const h3m = s.match(/^<h3[^>]*>([\s\S]*?)<\/h3>$/i);
    if (h3m) {
      const text = decodeHtml(h3m[1].replace(/<[^>]+>/g,''));
      if (text) result.push(h3(text));
      continue;
    }

    // UL/OL — processar LIs
    const ulm = s.match(/^<(?:ul|ol)[^>]*>([\s\S]*?)<\/(?:ul|ol)>$/i);
    if (ulm) {
      const lis = [...ulm[1].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)];
      for (const li of lis) {
        const runs = parseInlineRuns(li[1]);
        if (runs.length) result.push(new Paragraph({
          spacing: spacingPara(20, 80),
          numbering: { reference: 'bullets', level: 0 },
          children: runs
        }));
      }
      continue;
    }

    // P
    const pm = s.match(/^<p[^>]*>([\s\S]*?)<\/p>$/i);
    if (pm) {
      const inner = pm[1].trim();
      if (!inner) continue;
      const runs = parseInlineRuns(inner);
      if (runs.length) result.push(new Paragraph({
        alignment: AlignmentType.JUSTIFY,
        spacing: spacingPara(60, 160),
        children: runs
      }));
      continue;
    }

    // Texto puro / fallback
    const text = decodeHtml(s.replace(/<[^>]+>/g,'').trim());
    if (text && text.length > 1) result.push(new Paragraph({
      alignment: AlignmentType.JUSTIFY,
      spacing: spacingPara(60, 160),
      children: [new TextRun({ text, font: 'Arial', size: 22 })]
    }));
  }

  return result;
}

// ── Converte yyyy-mm-dd → dd/mm/yyyy (mantém outros formatos intactos) ────
function fmtDate(d) {
  if (!d) return d;
  const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : d;
}

// ── Construtor principal ──────────────────────────────────────────────────
async function buildDoc(data) {
  const cn    = (data.clientName   || '').toUpperCase();
  const cc    = (data.clientCity   || '').toUpperCase();
  const cu    = data.clientUnit    || '';
  const filial = data.clientFilial || '';
  const seg   = data.clientSegmento || '';
  const ctHW  = data.ctHardware    || '';
  const ctCl  = data.ctCloud       || '';
  const analyst = data.analystName || '';
  const rev   = data.docRevision   || 'Rev00';
  const revDate = fmtDate(data.docDate || '');
  const revDesc = data.revDesc     || 'Geração do documento';
  const mods  = data.mods          || {};
  const imgs  = data.guardianImgs  || {};
  const clientLogob64 = data.clientLogoB64 || '';
  const prixb64 = data.prixLogoB64 || '';
  const clientImgb64 = data.clientImgB64 || '';
  const clientDesc = data.clientDesc || '';

  const docFilename = `Descritivo Funcional_GuardianPRO_${data.clientName || 'Cliente'}_${rev}`;

  // ── Seções do documento ───────────────────────────────────────────────
  const sections = [];

  // ═══════════════════════════════════════════════════════
  // PÁGINA 1: CAPA
  // ═══════════════════════════════════════════════════════
  const capaContent = [];

  // Banner Guardian
  if (imgs.guardian_capa) {
    const bannerParas = imgPara(imgs.guardian_capa, 17.8, '', { before: 0, after: 120, hCm: 7.44 });
    if (bannerParas) capaContent.push(...bannerParas);
  }

  // Título
  capaContent.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: spacingPara(120, 120),
    children: [new TextRun({ text: 'DESCRITIVO FUNCIONAL', font: 'Cambria', size: 40, bold: true, color: C_AZUL_ESC })]
  }));

  // Subtítulo
  capaContent.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: spacingPara(0, 160),
    children: [new TextRun({ text: 'GUARDIAN PRO \u2014 Software para Gerenciamento de Operações de Pesagem', font: 'Cambria', size: 26, color: '222222' })]
  }));

  // Nome cliente
  if (cn) {
    capaContent.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: spacingPara(60, 20),
      children: [new TextRun({ text: cn + (cc ? ` \u2014 ${cc}` : ''), font: 'Cambria', size: 32, bold: true, color: C_AZUL_ESC })]
    }));
  }

  if (cu) {
    capaContent.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: spacingPara(0, 120),
      children: [new TextRun({ text: cu, font: 'Cambria', size: 26, color: '444444' })]
    }));
  }

  // Tabela identificação: FAZENDA | CT/OV | CT CLOUD
  capaContent.push(emptyPara(60, 20));
  const idW = Math.floor(CW / 3);
  const idW3 = CW - idW * 2;
  capaContent.push(new Table({
    width: { size: CW, type: WidthType.DXA },
    columnWidths: [idW, idW, idW3],
    rows: [
      new TableRow({ children: [
        tc('FAZENDA / UNIDADE',       idW,  { header: true, align: AlignmentType.CENTER }),
        tc('CT/OV HARDWARE E SERVIÇOS', idW, { header: true, align: AlignmentType.CENTER }),
        tc('CT CLOUD',                 idW3, { header: true, align: AlignmentType.CENTER }),
      ]}),
      new TableRow({ children: [
        tc((cn || '\u2014') + (cu ? ' / ' + cu : ''), idW, { fill: C_BRANCO, align: AlignmentType.CENTER }),
        tc(ctHW || '\u2014', idW,  { fill: C_BRANCO, align: AlignmentType.CENTER }),
        tc(ctCl || '\u2014', idW3, { fill: C_BRANCO, align: AlignmentType.CENTER }),
      ]})
    ]
  }));

  // Logo do cliente na capa (após tabela CT/OV), ~5cm altura, centralizado
  if (clientLogob64) {
    try {
      const b64cov = clientLogob64.includes('base64,') ? clientLogob64.split('base64,')[1] : clientLogob64;
      const bufCov = Buffer.from(b64cov, 'base64');
      const extCov = clientLogob64.startsWith('data:image/jpeg') ? 'jpg' : 'png';
      const ratio  = getImageAspectRatio(bufCov, extCov);           // h/w
      const hCov   = 5.0;                                           // altura fixa ~5cm
      const wCov   = Math.min(hCov / ratio, 14.0);                  // largura proporcional, máx 14cm
      const covPars = imgPara(clientLogob64, wCov, '', { before: 80, after: 40, hCm: hCov });
      if (covPars) capaContent.push(...covPars);
    } catch (e) {
      process.stderr.write(`Logo capa falhou: ${e.message}\n`);
    }
  }

  // Filial e segmento
  const infoLine = [filial ? `FILIAL(IS): ${filial.toUpperCase()}` : '', seg ? `SEGMENTO: ${seg.toUpperCase()}` : ''].filter(Boolean).join('   |   ');
  if (infoLine) {
    capaContent.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: spacingPara(30, 20),
      children: [new TextRun({ text: infoLine, font: 'Cambria', size: 20, color: '444444' })]
    }));
  }

  // URL
  capaContent.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: spacingPara(120, 60),
    children: [new ExternalHyperlink({
      link: 'http://www.toledobrasil.com/produto/guardian',
      children: [new TextRun({ text: 'www.toledobrasil.com/produto/guardian', font: 'Cambria', size: 20, color: C_AZUL_MED })]
    })]
  }));

  capaContent.push(blueHline(8));
  capaContent.push(pageBreak());

  // ═══════════════════════════════════════════════════════
  // PÁGINA 2: INFO DO DOCUMENTO + HISTÓRICO
  // ═══════════════════════════════════════════════════════
  capaContent.push(sectionTitle('Informações do Documento'));
  capaContent.push(emptyPara(20, 20));

  const LW = Math.floor(CW * 0.35);
  const VW = CW - LW;
  capaContent.push(infoTable([
    ['Título do Documento', 'Descritivo Funcional'],
    ['Autor', analyst || '\u2014'],
    ['Nome do Arquivo', docFilename],
  ], LW, VW));

  capaContent.push(emptyPara(80, 20));
  capaContent.push(sectionTitle('Histórico de Revisões'));
  capaContent.push(emptyPara(20, 20));

  const RW = [Math.floor(CW*0.15), Math.floor(CW*0.10), Math.floor(CW*0.50), CW - Math.floor(CW*0.15) - Math.floor(CW*0.10) - Math.floor(CW*0.50)];
  capaContent.push(makeTable(
    ['Data', 'Rev.', 'Descrição', 'Autor'],
    [[revDate || '\u2014', rev, revDesc, analyst || '\u2014']],
    RW
  ));

  capaContent.push(emptyPara(80, 20));
  capaContent.push(blueHline(6));
  capaContent.push(pageBreak());

  // ═══════════════════════════════════════════════════════
  // PÁGINA 3: ÍNDICE
  // ═══════════════════════════════════════════════════════
  capaContent.push(new Paragraph({
    spacing: spacingPara(0, 80),
    children: [new TextRun({ text: 'Índice', font: 'Arial Black', size: 28, bold: true, color: C_AZUL_ESC })]
  }));
  capaContent.push(new TableOfContents('Índice', { hyperlink: true, headingStyleRange: '1-3' }));
  capaContent.push(pageBreak());

  // ═══════════════════════════════════════════════════════
  // SEÇÃO 1: PERFIL DO CLIENTE (página dedicada, logo após o Índice)
  // ═══════════════════════════════════════════════════════
  capaContent.push(h1('1) Perfil do Cliente'));
  capaContent.push(emptyPara(20, 20));

  // Imagem da unidade/planta do cliente (centralizada, largura máx 14cm)
  if (clientImgb64) {
    try {
      const b64clean = clientImgb64.includes('base64,') ? clientImgb64.split('base64,')[1] : clientImgb64;
      const bufImg   = Buffer.from(b64clean, 'base64');
      const extImg   = clientImgb64.startsWith('data:image/jpeg') ? 'jpg' : 'png';
      const ratio    = getImageAspectRatio(bufImg, extImg);  // h/w
      const wImg     = 14.0;
      const hImg     = Math.min(wImg * ratio, 10.0);
      const imgPars  = imgPara(clientImgb64, wImg, '', { before: 40, after: 60, hCm: hImg });
      if (imgPars) capaContent.push(...imgPars);
    } catch (e) {
      process.stderr.write(`Imagem perfil cliente falhou: ${e.message}\n`);
    }
  }

  // Texto descritivo do cliente
  if (clientDesc) {
    // Quebra por parágrafos (o campo pode conter \n ou \n\n)
    const descParas = clientDesc.split(/\n+/).map(t => t.trim()).filter(t => t.length > 0);
    for (const txt of descParas) {
      capaContent.push(new Paragraph({
        alignment: AlignmentType.JUSTIFY,
        spacing: spacingPara(40, 40),
        children: [new TextRun({ text: txt, font: 'Arial', size: 22 })]
      }));
    }
  }

  // Referências documentais (OV / CT)
  const clientNameRef = data.clientName || 'o Cliente';
  capaContent.push(new Paragraph({
    alignment: AlignmentType.JUSTIFY,
    spacing: spacingPara(60, 40),
    children: [new TextRun({ text: `Este descritivo foi elaborado com base nas reuniões de levantamento de requisitos realizadas entre a Toledo do Brasil e ${clientNameRef}, tendo como referência:`, font: 'Arial', size: 22 })]
  }));
  if (data.ctHardware) capaContent.push(new Paragraph({
    spacing: spacingPara(20, 20),
    numbering: { reference: 'bullets', level: 0 },
    children: [
      new TextRun({ text: 'Ordem de Venda / Contrato de Hardware e Serviços: ', font: 'Arial', size: 22 }),
      new TextRun({ text: data.ctHardware, font: 'Arial', size: 22, bold: true })
    ]
  }));
  if (data.ctCloud) capaContent.push(new Paragraph({
    spacing: spacingPara(20, 20),
    numbering: { reference: 'bullets', level: 0 },
    children: [
      new TextRun({ text: 'Contrato Licenciamento Cloud Prix: ', font: 'Arial', size: 22 }),
      new TextRun({ text: data.ctCloud, font: 'Arial', size: 22, bold: true })
    ]
  }));

  capaContent.push(pageBreak());

  // ═══════════════════════════════════════════════════════
  // CONTEÚDO HTML (seções técnicas geradas pelo builder)
  // ═══════════════════════════════════════════════════════
  // imgs passado para htmlToParas resolver <img data-gimg="chave"> inline
  const htmlParas = htmlToParas(data.htmlContent || '', imgs);
  capaContent.push(...htmlParas);

  // ── Montar documento ────────────────────────────────────────────────
  const header = buildHeader(clientLogob64, prixb64);
  const footer = buildFooter(docFilename);

  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: 'Arial', size: 22 } }
      },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: 'Arial Black', size: 26, bold: true, color: C_BRANCO },
          paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: 'Arial Black', size: 24, bold: true, color: C_AZUL_ESC },
          paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 1 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: 'Arial', size: 22, bold: true, color: C_AZUL_MED },
          paragraph: { spacing: { before: 120, after: 40 }, outlineLevel: 2 } },
      ]
    },
    numbering: {
      config: [{
        reference: 'bullets',
        levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
      }]
    },
    sections: [{
      properties: pageProps(),
      headers: { default: header },
      footers: { default: footer },
      children: capaContent
    }]
  });

  return await Packer.toBuffer(doc);
}

// Original PPTX authoring source. Requires @oai/artifact-tool.
// The normal Python corpus build verifies and retains the committed PPTX bytes.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const buildDir = path.join(root, "datasets/.qa/deck");
await fs.mkdir(buildDir, { recursive: true });
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
function text(slide, value, x, y, w, h, size, color = "#000000", bold = false) {
  const shape = slide.shapes.add({ geometry: "textbox", position: { left:x, top:y, width:w, height:h }, fill:"none", line:{fill:"none",width:0} });
  shape.text = value;
  shape.text.style = { typeface:"Overused Grotesk", fontSize:size, bold, color, autoFit:"none" };
  return shape;
}
function base(number, dark = false) {
  const slide = deck.slides.add();
  slide.background.fill = dark ? "#3E18F9" : "#F5F5F5";
  text(slide, "NORTH FERN / FICTIONAL COMPANY", 76, 42, 1090, 32, 18, dark ? "#FFFFFF" : "#3E18F9");
  text(slide, "SYNTHETIC EXAMPLE / ALL FIGURES ARE FICTIONAL", 76, 659, 1010, 24, 14, dark ? "#FFFFFF" : "#737373");
  text(slide, String(number).padStart(2,"0"), 1150, 656, 54, 26, 17, dark ? "#FFFFFF" : "#737373");
  slide.speakerNotes.textFrame.setText("First-party synthetic document for testing document classification. The company, customers, financial figures and fundraising request are fictional. Visual direction: https://www.llamaindex.ai/brand. This is a source document, not a product performance claim.");
  return slide;
}
let slide = base(1, true);
text(slide, "Equipment maintenance\nfor independent teams", 76, 182, 1100, 180, 64, "#FFFFFF", true);
text(slide, "Seed investor presentation", 78, 399, 1050, 58, 30, "#FFFFFF");
text(slide, "SEPTEMBER 2026", 78, 496, 900, 35, 20, "#37D7FA");
slide = base(2);
text(slide, "A shared maintenance record", 76, 118, 1120, 85, 49, "#000000", true);
text(slide, "Service teams lose time reconstructing equipment history from scattered spreadsheets.", 76, 242, 1000, 105, 31);
text(slide, "North Fern combines service logs and maintenance schedules in one subscription product.", 76, 380, 1000, 104, 31);
text(slide, "Illustrative annual price: $12,000 per team", 76, 554, 1100, 55, 25, "#3E18F9");
slide = base(3);
text(slide, "Seed financing plan", 76, 118, 1120, 82, 49, "#000000", true);
text(slide, "$2 million", 76, 226, 1090, 100, 76, "#3E18F9", true);
text(slide, "Illustrative capital request", 78, 340, 1000, 48, 26);
text(slide, "Fund twelve months of product development and a small paid pilot with service firms managing 50 to 500 assets.", 76, 426, 1080, 123, 30);
text(slide, "Founding team: field operations and software engineering", 76, 574, 1100, 45, 24, "#737373");

await (await PresentationFile.exportPptx(deck)).save(path.join(buildDir, "candidate.pptx"));
for (const [i, s] of [...deck.slides.items].entries()) {
  const blob = await deck.export({ slide:s, format:"png", scale:1 });
  await fs.writeFile(path.join(buildDir, `slide-${i+1}.png`), new Uint8Array(await blob.arrayBuffer()));
}
console.log(path.join(buildDir, "candidate.pptx"));

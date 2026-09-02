// An example plugin view.
//
// A plugin view is an ES module with a default export taking the root element,
// exactly like OmaCar's own views. It may import from ../../js/core.js for the
// helpers, or use plain DOM -- nothing is required of it beyond the default
// export, and nothing is bundled.
export default function fuelLog(root) {
  const box = document.createElement("section");
  box.className = "card";
  box.innerHTML =
    '<div class="eyebrow">Plugin</div>' +
    '<div class="title">Fuel log</div>' +
    '<p class="lede">Fill-ups recorded with <code>omacar fuel add</code>. ' +
    'This screen comes from a plugin directory, not from OmaCar.</p>';
  root.appendChild(box);
}

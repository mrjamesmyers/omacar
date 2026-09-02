// The document library.
//
// A car's history is not only what its computers remember. It is the oil change
// receipt, the registration renewal, the inspection certificate, the citation.
// That paper is what a buyer asks for and what a warranty claim needs, and it
// is also what gets lost.
//
// TWO RULES SHAPE THIS SCREEN.
//
// The original is never replaced. Whatever the advisor reads out of a document
// is shown NEXT TO it and labelled as extracted, because OCR of a crumpled
// receipt is a guess and the scan is not. Anything it filled in can be edited,
// and editing wins permanently.
//
// Nothing is extracted without being asked. Uploading a document files it;
// reading it costs an advisor call and a few seconds, and that is a decision
// rather than something that happens to your whole glovebox at once.

import { h, store, api, toast, shortDate, confirmDialog } from "../core.js";
import { explain } from "../learn.js";

const KIND_LABEL = {
  service: "Service", receipt: "Receipt", registration: "Registration",
  insurance: "Insurance", inspection: "Inspection", citation: "Citation",
  warranty: "Warranty", manual: "Manual", other: "Other",
};

export default function documents(root) {
  let docs = [];
  let kinds = {};
  let totals = {};
  let filter = "";
  let busy = null;

  const wrap = h("div.docs");
  root.appendChild(wrap);

  async function load() {
    try {
      const r = await api.documents();
      docs = r.documents || [];
      kinds = r.kinds || {};
      totals = r.totals || {};
    } catch (e) {
      toast("Could not read the library: " + (e.message || e), "bad");
    }
    draw();
  }

  async function upload(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const r = await api.document({
          action: "add", file: reader.result, filename: file.name,
          kind: "other",
        });
        if (r.duplicate) toast("Already filed — this is the same document.");
        else toast(`Filed ${r.title || file.name}.`);
        await load();
      } catch (e) {
        toast("Could not file it: " + (e.message || e), "bad");
      }
    };
    reader.readAsDataURL(file);
  }

  async function parse(d) {
    busy = d.id;
    draw();
    try {
      const r = await api.document({ action: "parse", id: d.id });
      const got = r.extracted || {};
      toast(got.unreadable
        ? "The text was too poor to trust — nothing was filled in."
        : `Read it: ${got.title || "no title"}${got.amount ? " · $" + got.amount : ""}`);
      await load();
    } catch (e) {
      toast(String(e.message || e), "bad");
    } finally {
      busy = null;
      draw();
    }
  }

  async function save(id, field, value) {
    try {
      await api.document({ action: "update", id, [field]: value });
      await load();
    } catch (e) {
      toast("Could not save: " + (e.message || e), "bad");
    }
  }

  async function remove(d) {
    const ok = await confirmDialog({
      title: "Remove this document?",
      body: h("div.sect",
        h("p.lede", `“${d.title}” and its file will be deleted from the library.`),
        h("p.lede", "This does not touch the original wherever you got it from, "
          + "but OmaCar's copy is gone.")),
      confirm: "Remove",
    });
    if (!ok) return;
    await api.document({ action: "remove", id: d.id });
    toast("Removed.");
    await load();
  }

  function money(v) {
    return v == null ? "" : "$" + Number(v).toFixed(2);
  }

  function card(d) {
    const ex = d.extracted || null;
    const isBusy = busy === d.id;
    const fields = [
      ["title", "Title", d.title],
      ["vendor", "Vendor", d.vendor],
      ["doc_date", "Date", d.doc_date],
      ["amount", "Amount", d.amount],
      ["odometer", "Odometer", d.odometer],
    ];

    return h("section.card",
      h("div.row.wrapline",
        h("div", { style: { minWidth: "0" } },
          h("div.title", d.title || "Untitled"),
          h("div.sub.row.wrapline", { style: { gap: "10px" } },
            h("span.pill", KIND_LABEL[d.kind] || d.kind),
            d.doc_date ? h("span", d.doc_date) : null,
            d.vendor ? h("span", d.vendor) : null,
            d.amount != null ? h("span.mono", money(d.amount)) : null,
            d.odometer != null ? h("span.mono", Math.round(d.odometer) + " mi") : null)),
        h("div.right.row.wrapline", { style: { gap: "8px" } },
          h("a.btn.ghost", { href: "/doc/" + d.file, target: "_blank" }, "Open"),
          h("button.btn" + (ex ? ".ghost" : ""), {
            disabled: isBusy,
            onclick: () => parse(d),
          }, isBusy ? "Reading…" : ex ? "Read again" : "Read it"),
          h("button.btn.ghost", { onclick: () => remove(d) }, "Remove"))),

      // Editable fields. Typing here beats anything extracted, permanently.
      h("div.doc-fields",
        ...fields.map(([field, label, val]) => {
          const input = h("input.input", {
            type: "text", value: val == null ? "" : String(val),
            "aria-label": label,
            onchange: (e) => save(d.id, field, e.target.value),
          });
          return h("label.doc-field", h("span.doc-k", label), input);
        }),
        h("label.doc-field",
          h("span.doc-k", "Kind"),
          h("select.input", {
            onchange: (e) => save(d.id, "kind", e.target.value),
          }, ...Object.keys(kinds).map((k) =>
            h("option", { value: k, selected: k === d.kind ? "" : null },
              KIND_LABEL[k] || k))))),

      ex
        ? h("details.doc-ex",
            h("summary", `What the advisor read${ex._read_by ? " (" + ex._read_by + ")" : ""}`
              + (ex.confidence ? ` — ${ex.confidence} confidence` : "")),
            h("div.doc-ex-body",
              ex.unreadable
                ? h("p.lede.warn", "The text was too poor to trust.")
                : null,
              (ex.service_items || []).length
                ? h("p.lede", "Work done: " + ex.service_items.join(", "))
                : null,
              (ex.items || []).length
                ? h("ul.tight", ...ex.items.map((i) =>
                    h("li", `${i.description || ""} ${i.amount != null ? money(i.amount) : ""}`)))
                : null,
              h("p.sub", "Extracted, not typed. Edit any field above to correct "
                + "it — what you type is kept.")))
        : null);
  }

  function draw() {
    while (wrap.firstChild) wrap.removeChild(wrap.firstChild);

    const ex = explain(h, "documents");
    if (ex) wrap.appendChild(ex);

    const picker = h("input", {
      type: "file", hidden: true,
      accept: ".pdf,.png,.jpg,.jpeg,.webp,.heic,.txt,application/pdf,image/*,text/plain",
      onchange: (e) => { upload(e.target.files[0]); e.target.value = ""; },
    });

    wrap.appendChild(h("section.card",
      h("div.row.wrapline",
        h("div",
          h("div.eyebrow", "Kept with this car"),
          h("div.title", "Documents"),
          h("p.lede", totals.count
            ? `${totals.count} document${totals.count === 1 ? "" : "s"}`
              + (totals.spend ? ` · ${money(totals.spend)} recorded` : "")
              + (totals.earliest ? ` · ${totals.earliest} to ${totals.latest}` : "")
            : "Receipts, registrations, inspections, citations — anything that "
              + "belongs with the car rather than in a drawer.")),
        h("div.right",
          h("button.btn.primary", { onclick: () => picker.click() },
            "Add a document"))),
      picker));

    if (Object.keys(totals.by_kind || {}).length > 1) {
      wrap.appendChild(h("div.doc-filters",
        h("button.btn.sm" + (filter ? "" : ".on"),
          { onclick: () => { filter = ""; draw(); } }, "All"),
        ...Object.entries(totals.by_kind).map(([k, n]) =>
          h("button.btn.sm" + (filter === k ? ".on" : ""), {
            onclick: () => { filter = k; draw(); },
          }, `${KIND_LABEL[k] || k} ${n}`))));
    }

    const shown = filter ? docs.filter((d) => d.kind === filter) : docs;
    if (!shown.length) {
      wrap.appendChild(h("section.card",
        h("p.lede", docs.length
          ? "Nothing of that kind yet."
          : "Nothing filed yet. Add a photograph of a receipt and press "
            + "“Read it” — a phone picture is usually enough.")));
      return;
    }
    for (const d of shown) wrap.appendChild(card(d));
  }

  draw();
  load();
}

#set document(title: "Technical Architecture & Evaluation Report", author: "Engineering Team")
#set page(
  paper: "a4",
  margin: (left: 2.5cm, right: 2.5cm, top: 2.5cm, bottom: 2.5cm),
  numbering: "1 / 1",
  number-align: right,
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 8.5pt, fill: luma(110))
      Technical Architecture & Evaluation Report #h(1fr) #datetime.today().display("[year]-[month]-[day]")
      #line(length: 100%, stroke: 0.4pt + luma(190))
    ]
  },
)
#set text(font: ("Times New Roman", "Calibri", "Segoe UI"), size: 10.5pt, fill: luma(25))
#set par(justify: true, leading: 0.72em, spacing: 0.85em)
#set heading(numbering: "1.1 ")
#show heading.where(level: 1): it => {
  v(14pt)
  text(size: 14pt, weight: "bold", fill: rgb("#1E3A8A"))[#it]
  v(4pt)
}
#show heading.where(level: 2): it => {
  v(10pt)
  text(size: 12pt, weight: "bold", fill: rgb("#1F2937"))[#it]
  v(2pt)
}

#align(center)[
  #v(1cm)
  #text(size: 18pt, weight: "bold", fill: rgb("#1E3A8A"))[Technical Architecture & System Report]
  #v(0.3cm)
  #text(size: 11pt, style: "italic", fill: luma(80))[Deterministic Layout Powered by Typst + Zero-Overlap Draw.io]
  #v(0.6cm)
  #line(length: 60%, stroke: 1pt + rgb("#1D4ED8"))
  #v(0.8cm)
]

#outline(title: [Table of Contents], indent: auto)

= Executive Summary
This modern technical report template guarantees deterministic spacing, exact margins, crisp vector figures, and millisecond compilation for living engineering documentation.

= System Architecture & Metrics
#figure(
  table(
    columns: (auto, 1fr, auto, auto),
    inset: 7pt,
    align: (left, left, right, center),
    stroke: (x: none, y: 0.5pt + luma(180)),
    fill: (_, row) => if row == 0 { rgb("#EFF6FF") } else { none },
    [*Component*], [*Responsibility*], [*Latency*], [*Status*],
    [API Gateway], [Auth, rate-limiting, request envelope], [4.2 ms], [Verified],
    [Workflow Engine], [Config-driven SOP state transitions], [11.8 ms], [Verified],
    [Audit Chain], [Tamper-evident hash-linked ledger], [2.1 ms], [Verified],
  ),
  caption: [Verified subsystem performance baseline.]
)

= Conclusion
Every diagram, table, and equation in this report can be regenerated automatically whenever the underlying codebase evolves.

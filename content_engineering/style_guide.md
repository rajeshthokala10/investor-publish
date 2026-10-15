# Style guide

- British/Indian English spelling; IST timestamps with offset (`2026-10-15T06:00:00+05:30`).
- Money: ₹ with lakh/crore (`₹1.20 cr`, `₹85.0 lakh`), rates as `₹9,500/sq ft (super built-up, developer quote)`.
- Status labels exactly as in `harness/report.py::STATUS` with symbol + word (never colour alone).
- Corridor names exactly as `config/corridors.yaml` `name`; note straddling once per section.
- Tables: claim → where → published → status → source (with claim ID in code font).
- Plain verbs: "says", "reports", "quotes". Avoid "skyrocket", "hot", "booming" unless quoting.
- Infographic (cover page; template in `templates/report.css` + `harness/infographic.py`):
  navy serif headline with numbers in red; subtitle with window and lead source status;
  skyline hero with East corridor pins + 2 KPI tiles; row of chart / highlights / growth
  drivers; row of chart / type matrix / outlook; corridor card strip; source footer.
  Charts: one measure each, bars coloured by region identity (blue East, orange North,
  aqua South, yellow West, violet Peripheral), direct value labels, legend when >1 region,
  hover titles in HTML. Generated SVG illustrations only, never stock photos.

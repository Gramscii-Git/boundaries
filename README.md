# Boundaries

Ready-to-draw administrative boundaries for Italy and for the countries
of Europe and the world, as SVG paths in plain JSON. Every shape carries
the identifiers statistical providers use for that place, so a table of
numbers keyed by ISTAT code, NUTS code, licence plate or ISO code can be
coloured on a map without a lookup step.

Five files, 8,264 shapes, 2.0 MB in total. No runtime, no dependencies:
a file is a JSON document a browser can draw with one `<svg>` element.

| File | Shapes | Level | Identifiers on each shape | Source | Licence |
| --- | ---: | --- | --- | --- | --- |
| `italy-regions.geo.json` | 22 | Italian regions, plus the autonomous provinces of Trento and Bolzano | ISTAT region code (`03`), NUTS 2 code (`ITC4`), upper-case name (`LOMBARDIA`) | ISTAT, 1 January 2026 | CC BY 4.0 |
| `italy-provinces.geo.json` | 110 | Italian provinces and metropolitan cities | ISTAT province code (`015`), NUTS 3 code (`ITC4C`), licence plate (`MI`) | ISTAT, 1 January 2026 | CC BY 4.0 |
| `italy-municipalities.geo.json` | 7,896 | Italian municipalities | ISTAT municipality code (`015146`); 377 municipalities also carry the code they had under an earlier provincial layout | ISTAT, 1 January 2026 | CC BY 4.0 |
| `europe.geo.json` | 59 | Countries of Europe and its margins | ISO 3166-1 alpha-2 (`DE`), alpha-3 (`DEU`), and the Eurostat code where it differs (`EL`, `UK`) | Natural Earth, 1:50m | Public domain |
| `world.geo.json` | 177 | Countries of the world | ISO 3166-1 alpha-2, alpha-3, and the Eurostat code where it differs | Natural Earth, 1:50m | Public domain |

The shapes carry no population, area, postal code or cadastral code.
They are simplified for drawing at screen resolution and are not
suitable for measuring areas, distances or legal boundaries.

## Format

Each file is one JSON object:

```json
{
  "viewBox": "0 0 1000 1288.1",
  "source": "ISTAT, Confini delle unità amministrative a fini statistici, 1 gennaio 2026 (generalizzati), CC BY 4.0",
  "shapes": [
    { "name": "Piemonte", "aliases": ["01", "ITC1", "PIEMONTE"], "d": "M319.8,52.4L…Z" }
  ]
}
```

- `viewBox` is the SVG view box every path in the file is drawn into.
  The three Italian files share one view box and one projection, so a
  region, a province and a municipality drawn together line up.
- `source` names the upstream dataset and its licence, so a file copied
  on its own still says where it came from.
- `shapes[].name` is the official name of the place.
- `shapes[].aliases` are the identifiers the place is known by. Match a
  row of data against any of them.
- `shapes[].d` is the SVG path, already projected and simplified.

To draw a file:

```html
<svg viewBox="0 0 1000 1288.1">
  <path d="…" fill="#dfe6ee" stroke="#fff" stroke-width="0.5" />
</svg>
```

## How the files were made

### Italy

Source: ISTAT, *Confini delle unità amministrative a fini statistici al
1° gennaio 2026*, the generalised release (`Limiti01012026_g`), read from
the shapefiles `Reg01012026_g`, `ProvCM01012026_g` and `Com01012026_g`.
The coordinates in that release are UTM zone 32N eastings and northings.

1. One transform is computed from Italy's own bounding box and applied to
   all three levels: the country is drawn 1,000 units wide, the height
   follows from its shape, nothing is stretched.
2. Each polygon is simplified with topology preserved, with a tolerance
   of 250 metres for regions and provinces and 500 metres for
   municipalities. At this width one unit is about one kilometre, so a
   boundary moves by less than a pixel.
3. Each polygon is written as an SVG path with one decimal of precision.
4. Identifiers are attached from ISTAT's own classification: region,
   province and municipality codes, NUTS codes, licence plates, and for
   municipalities the codes they carried under an earlier provincial
   layout, so data keyed by either vintage lands on the same shape.

### Europe and the world

Source: Natural Earth, *Admin 0 – Countries*, 1:50m scale.

1. The country polygons are projected: Lambert azimuthal equal-area for
   `europe.geo.json`, which keeps the European polygons only, and
   Robinson for `world.geo.json`.
2. Each polygon is simplified for screen resolution and written as an
   SVG path in a 1,000-unit-wide view box.
3. ISO 3166-1 alpha-2 and alpha-3 codes are attached, plus the Eurostat
   country code where it differs from ISO (`EL` for Greece, `UK` for the
   United Kingdom), so Eurostat tables colour the map directly.

The Natural Earth release archive these two files were made from is not
pinned by checksum. Regenerating them means recording that input first.

## Integrity

The files distributed here are identified by these SHA-256 digests, also
listed in `SHA256SUMS`. They identify the adapted files in this
repository, not the upstream archives.

| File | SHA-256 |
| --- | --- |
| `italy-regions.geo.json` | `44575f58980d226aa5ab3bec7b9daad24344462d5c3f5a0052485a17f4290601` |
| `italy-provinces.geo.json` | `292b3a4bd42844846519e8271466d23e96cf207861cad858e1c238da416ca798` |
| `italy-municipalities.geo.json` | `c0759f670a54920772b2cafd1541717e34c17b2a44cb970d0a7f05a502673420` |
| `europe.geo.json` | `a4f787145ac330c17426ec734d3784d0d13665e2fdf98ab76fc8b976572492d3` |
| `world.geo.json` | `13d478295fa33bb49531878f637188559b570c3b673df6f8b1b458e7f444af62` |

```sh
shasum -a 256 -c SHA256SUMS
```

## Licences

Every file in this repository is released by Gramscii under the
[Creative Commons Attribution 4.0 International](LICENSE)
licence. You may copy, redistribute, adapt and use the files for any
purpose, including commercially, as long as you give credit.

Each file also carries the terms of the dataset it was adapted from,
which do not change under this release:

- `italy-regions.geo.json`, `italy-provinces.geo.json`,
  `italy-municipalities.geo.json` are adapted from ISTAT data published
  under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The
  attribution ISTAT asks for is:

  > ISTAT, Confini delle unità amministrative a fini statistici,
  > 1 gennaio 2026 (generalizzati), CC BY 4.0

  ISTAT's open-data terms: <https://www.istat.it/dati/open-data/>.

- `europe.geo.json` and `world.geo.json` are adapted from Natural Earth
  data, which its authors place in the
  [public domain](NATURAL-EARTH.md). No attribution is required
  by the source; Natural Earth welcomes it.

When you use a file, credit both the file's source, as written in its
`source` field, and this repository:

> Boundaries by Gramscii, CC BY 4.0, https://github.com/Gramscii-Git/boundaries

## Origin

These files are the map layer of Semantic Deterministic Graph,
Gramscii's deterministic answer engine, and are published here on their own so
that anyone drawing Italian or European statistics can use them. The
copies inside that project and the files here are byte-identical: the
digests above are the proof.

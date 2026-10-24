# Boundary lines for the maps

Drawn on every map by `scripts/scoring/boundaries.py`; built by
`scripts/preprocess/make_boundaries.py` (clipped to 50-100°E, 5°S-40°N, simplified; the
command is in that script). Lines only, longitude/latitude (WGS 84).

| File | What | Source | Licence |
|---|---|---|---|
| `india_outline.geojson` | coast and land boundary of India, as depicted by the Survey of India | DataMeet Community Maps Project, [`Country/india-composite.geojson`](https://github.com/datameet/maps/tree/master/Country), compiled from LSIB (U.S. Department of State), Alhasan Systems and Natural Earth | CC0 |
| `india_states.geojson` | boundaries between the 36 states and union territories (present-day, after 2020), ending at the coast | DataMeet Community Maps Project, [`States/Admin2`](https://github.com/datameet/maps/tree/master/States), from Election Commission of India maps | CC BY 2.5 India (project page) / CC BY 4.0 (repository): attribution below |
| `neighbours.geojson` | coasts and borders of the other countries, without their segments along India's land boundary | [Natural Earth](https://www.naturalearthdata.com) 1:10m admin 0 countries, India point of view (`ne_10m_admin_0_countries_ind`) | public domain |

Attribution: *State boundaries of India by the [DataMeet India community](http://datameet.org/)
([github.com/datameet/maps](https://github.com/datameet/maps)), CC BY.* Made with Natural Earth.

Notes
- The state boundaries are today's, also on the 1924 maps; they are drawn for orientation only.
- The coast of India is detailed enough for the 3 km maps (Mumbai harbour and Thane creek are
  water); the 0.4 km simplification is below the 3 km grid spacing.
- Model results never depend on these lines: scoring uses the IMD grid's own land points.

# Coronados System

## Data Storage (SQLite)
The app now uses a SQLite database file:
- `coronados.db`

Database and tables are created automatically when the app loads storage functions.

## Schema
Tables preserve the same functional fields used in the previous CSV model.

### `cierres`
- `id` (INTEGER, PK AUTOINCREMENT)
- `fecha` (TEXT)
- `turno` (TEXT)
- `inicio_caja` (REAL)
- `efectivo` (REAL)
- `posnet` (REAL)
- `transferencias` (REAL)
- `pedidosya` (REAL)
- `gastos` (REAL)
- `efectivo_neto` (REAL)
- `total_turno` (REAL)
- `valor_z` (REAL)

### `gastos`
- `id` (INTEGER, PK AUTOINCREMENT)
- `fecha` (TEXT)
- `proveedor` (TEXT)
- `monto` (REAL)
- `categoria` (TEXT)

### `sueldos`
- `id` (INTEGER, PK AUTOINCREMENT)
- `fecha` (TEXT)
- `empleado` (TEXT)
- `monto` (REAL)

### `pedidosya`
- `id` (INTEGER, PK AUTOINCREMENT)
- `fecha` (TEXT)
- `monto` (REAL)
- `metodo_pago` (TEXT)
- `comentarios` (TEXT)

### `transferencias`
- `id` (INTEGER, PK AUTOINCREMENT)
- `fecha` (TEXT)
- `alias_app` (TEXT)
- `monto` (REAL)
- `comentario` (TEXT)

## CSV to SQLite Migration
A migration script is included:
- `scripts/migrate_csv_to_sqlite.py`

It imports existing CSV files if present:
- `cierres.csv`
- `gastos.csv`
- `sueldos.csv`
- `pedidosya.csv`
- `transferencias.csv`

Default behavior:
- imports only into empty DB tables
- skips missing CSV files
- does not overwrite existing DB data

Run migration:
```bash
python scripts/migrate_csv_to_sqlite.py
```

Force overwrite DB tables from CSV:
```bash
python scripts/migrate_csv_to_sqlite.py --force
```

## Notes
- Streamlit UI behavior is preserved; storage calls still use the same `cargar_*` / `guardar_*` interface.
- Excel reference workbook filename: `Administracion Coronados.xlsx`

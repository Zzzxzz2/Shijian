// SQLite API timestamps without an offset represent UTC.
export function apiDate(value) {
  return new Date(typeof value === 'string' && /T/.test(value) && !/(Z|[+-]\d{2}:\d{2})$/i.test(value) ? value + 'Z' : value);
}

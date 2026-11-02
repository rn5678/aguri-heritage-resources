// Minimal, dependency-free D1 adapter for local development and direct Worker
// tests. Requires Node 22.13+ with node:sqlite (Node 24 recommended).
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';

export function createLocalDatabase(filename = ':memory:') {
  const database = new DatabaseSync(filename);
  database.exec(readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));
  const make = (sql, values = []) => {
    const execute = () => {
      const query = database.prepare(sql);
      const args = values.map(value => value instanceof ArrayBuffer ? new Uint8Array(value) : value);
      const results = query.columns().length ? query.all(...args) : [];
      const result = query.columns().length ? null : query.run(...args);
      return { success: true, results, meta: { changes: Number(result?.changes ?? database.prepare('SELECT changes() AS changes').get().changes) } };
    };
    return {
      bind(...args) { return make(sql, args); },
      async all() { return execute(); },
      async first(column) { const row = execute().results[0] || null; return column && row ? row[column] : row; },
      async run() { return execute(); },
      _execute: execute,
    };
  };
  return {
    prepare: make,
    exec(sql) { database.exec(sql); return { count: 1, duration: 0 }; },
    async batch(statements) {
      database.exec('BEGIN IMMEDIATE');
      try {
        const result = statements.map(statement => statement._execute());
        database.exec('COMMIT');
        return result;
      } catch (error) { database.exec('ROLLBACK'); throw error; }
    },
    close() { database.close(); },
  };
}

export class LocalD1 {
  constructor(filename = ':memory:') { return createLocalDatabase(filename); }
}

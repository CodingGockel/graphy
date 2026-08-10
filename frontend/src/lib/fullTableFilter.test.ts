import { describe, expect, it } from 'vitest';

import { filterFullTableRows } from './fullTableFilter';

const fullRows = [
	{ species: 'Tulipa sylvestris', garden: 'Botanischer Garten Jena', city: 'Jena', year: 2024 },
	{ species: 'Rosa canina', garden: 'Botanic Garden Berlin', city: 'Berlin', year: 2024 },
	{ species: 'Rosa canina', garden: 'Botanischer Garten Jena', city: 'Jena', year: 2023 }
];

describe('filterFullTableRows', () => {
	it('shows the complete Full Table before a user input is available', () => {
		expect(filterFullTableRows(fullRows, '')).toEqual(fullRows);
	});

	it('keeps every row whose city matches a word from the user question', () => {
		expect(filterFullTableRows(fullRows, 'zeige mir alle daten aus Jena')).toEqual([
			fullRows[0],
			fullRows[2]
		]);
	});

	it('requires all meaningful filter words to match the same row', () => {
		expect(filterFullTableRows(fullRows, 'zeige mir alle daten aus 2024 und aus Jena')).toEqual([
			fullRows[0]
		]);
	});

	it('matches values in every Full-Table column, including species names', () => {
		expect(filterFullTableRows(fullRows, 'Rosa canina')).toEqual([fullRows[1], fullRows[2]]);
	});
});

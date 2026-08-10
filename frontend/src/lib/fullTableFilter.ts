// Zerlegt Texte in vergleichbare Wörter. Akzente werden entfernt, damit
// z. B. "für" und "fur" beim Filtern gleich behandelt werden.
function words(value: unknown): string[] {
	return String(value ?? '')
		.normalize('NFKD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLocaleLowerCase()
		.match(/[\p{L}\p{N}]+/gu) ?? [];
}

// Häufige Wörter aus Fragen tragen nichts zum eigentlichen Tabellenfilter bei.
const ignoredQuestionWords = new Set([
	'alle', 'alles', 'an', 'aus', 'bei', 'bitte', 'das', 'daten', 'dem', 'den',
	'der', 'die', 'ein', 'eine', 'einen', 'einer', 'für', 'ich', 'im', 'in',
	'mir', 'mit', 'nach', 'über', 'und', 'von', 'was', 'welche', 'welchen',
	'zeige', 'zeig', 'zu'
]);

// Eine Zeile bleibt sichtbar, wenn sie alle relevanten Wörter der Frage enthält.
// Bei einer leeren Frage wird absichtlich die komplette Tabelle angezeigt.
export function filterFullTableRows(
	fullRows: Record<string, unknown>[],
	userQuestion: string
): Record<string, unknown>[] {
	const questionWords = new Set(
		words(userQuestion).filter((word) => word.length > 2 && !ignoredQuestionWords.has(word))
	);
	if (questionWords.size === 0) return fullRows;

	return fullRows.filter((row) => {
		const rowWords = new Set(Object.values(row).flatMap(words));
		return Array.from(questionWords).every((word) => rowWords.has(word));
	});
}

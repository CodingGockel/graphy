// Die möglichen Werte werden als Typen gesammelt, damit in den Komponenten
// keine ungültigen Einstellungen gespeichert werden können.
export type CsvSeparator = 'comma' | 'semicolon';
export type PreviewHeight = 'small' | 'medium' | 'large';
export type Language = 'en' | 'de';
export type Theme = 'light' | 'dark';

// Alle Einstellungen, die nur im Browser gespeichert werden.
export type AppSettings = {
	fastMode: boolean;
	csvSeparator: CsvSeparator;
	showQueryDefault: boolean;
	previewHeight: PreviewHeight;
	language: Language;
	theme: Theme;
};

// Ausgangswerte für neue Nutzer oder nach einem Zurücksetzen der Einstellungen.
export const defaultSettings: AppSettings = {
	fastMode: false,
	csvSeparator: 'comma',
	showQueryDefault: false,
	previewHeight: 'medium',
	language: 'en',
	theme: 'light'
};

// Liest die Einstellungen aus localStorage. Fehlt ein Wert, wird der Default genutzt.
export function loadSettings(): AppSettings {
	return {
		fastMode: JSON.parse(localStorage.getItem('fastMode') ?? JSON.stringify(defaultSettings.fastMode)),
		csvSeparator: (localStorage.getItem('csvSeparator') as CsvSeparator) ?? defaultSettings.csvSeparator,
		showQueryDefault: JSON.parse(
			localStorage.getItem('showQueryDefault') ?? JSON.stringify(defaultSettings.showQueryDefault)
		),
		previewHeight: (localStorage.getItem('previewHeight') as PreviewHeight) ?? defaultSettings.previewHeight,
		language: (localStorage.getItem('language') as Language) ?? defaultSettings.language,
		theme: (localStorage.getItem('theme') as Theme) ?? defaultSettings.theme
	};
}

// Speichert jede Einstellung einzeln, damit die Seiten sie direkt wieder laden können.
export function saveSettings(settings: AppSettings): void {
	localStorage.setItem('fastMode', JSON.stringify(settings.fastMode));
	localStorage.setItem('csvSeparator', settings.csvSeparator);
	localStorage.setItem('showQueryDefault', JSON.stringify(settings.showQueryDefault));
	localStorage.setItem('previewHeight', settings.previewHeight);
	localStorage.setItem('language', settings.language);
	localStorage.setItem('theme', settings.theme);
}

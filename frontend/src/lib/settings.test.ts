// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';

import { defaultSettings, loadSettings, saveSettings, type AppSettings } from './settings';

describe('settings storage', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('uses the defaults when no preferences have been saved', () => {
		expect(loadSettings()).toEqual(defaultSettings);
	});

	it('persists and restores every preference', () => {
		const settings: AppSettings = {
			fastMode: true,
			csvSeparator: 'semicolon',
			showQueryDefault: true,
			previewHeight: 'large',
			language: 'de',
			theme: 'dark'
		};

		saveSettings(settings);

		expect(loadSettings()).toEqual(settings);
	});
});

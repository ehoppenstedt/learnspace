import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLocales } from 'expo-localization';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { setApiLanguage } from '../api/client';
import en from './en';
import es from './es';

const STORAGE_KEY = 'ls.language';
export type Lang = 'es' | 'en';

function deviceLanguage(): Lang {
  const code = getLocales()[0]?.languageCode;
  return code === 'en' ? 'en' : 'es'; // Spanish is the default for everyone else
}

i18n.use(initReactI18next).init({
  resources: { es: { translation: es }, en: { translation: en } },
  lng: deviceLanguage(),
  fallbackLng: 'es',
  interpolation: { escapeValue: false },
  returnObjects: true,
});
setApiLanguage(i18n.language);

export async function restoreLanguage() {
  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEY);
    if (saved === 'es' || saved === 'en') await setLanguage(saved);
  } catch {
    // storage unavailable: keep device language
  }
}

export async function setLanguage(lang: Lang) {
  await i18n.changeLanguage(lang);
  setApiLanguage(lang);
  try {
    await AsyncStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // non-critical
  }
}

export default i18n;

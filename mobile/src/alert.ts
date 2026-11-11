import { Alert as RNAlert, Platform } from 'react-native';

type Btn = { text?: string; onPress?: () => void };

// react-native's Alert does nothing in a browser, so on web we use window.alert / window.confirm.
export const Alert = {
  alert(title: string, message?: string, buttons?: Btn[]) {
    if (Platform.OS !== 'web') return RNAlert.alert(title, message, buttons as any);
    const text = message ? `${title}\n\n${message}` : title;
    if (!buttons || buttons.length <= 1) {
      window.alert(text);
      buttons?.[0]?.onPress?.();
    } else if (window.confirm(text)) {
      buttons[0].onPress?.(); // OK = first button
    }
  },
};

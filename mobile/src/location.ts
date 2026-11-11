import * as Location from 'expo-location';

/** Asks permission, then returns the device position. Used for the "place and time" voting license. */
export async function currentPosition(): Promise<{ lat: number; lng: number }> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') throw new Error('Location permission is needed for this event.');
  if (!(await Location.hasServicesEnabledAsync())) {
    throw new Error('Turn on location services, then try again.');
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const p = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(
          'Could not get your location. Check location services and try again. On a simulator, set a simulated location.'
        )), 20000);
      }),
    ]);
    const { latitude: lat, longitude: lng } = p.coords;
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
      throw new Error('Your device returned an invalid location. Please try again.');
    }
    return { lat, lng };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

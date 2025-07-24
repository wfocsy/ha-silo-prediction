"""Platform for Silo Prediction sensor."""
import logging
import asyncio
import mysql.connector
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo # Python 3.9+ feature for timezone handling

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval

# Import DOMAIN from __init__.py if needed, or define it here for clarity
from . import DOMAIN # This imports DOMAIN from __init__.py

_LOGGER = logging.getLogger(__name__)

# Későbbi konfigurációhoz, ha a YAML-ben adjuk meg:
# platform_schema = PLATFORM_SCHEMA.extend({
#     vol.Required("monitored_entity_id"): cv.entity_id,
#     vol.Required("db_host"): cv.string,
#     vol.Required("db_user"): cv.string,
#     vol.Required("db_password"): cv.string,
#     vol.Required("db_name"): cv.string,
# })

SCAN_INTERVAL = timedelta(hours=12) # Naponta 2x-es frissítés

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Silo Prediction sensor platform."""
    _LOGGER.debug("Setting up SiloPredictionSensor platform.")

    # Jelenleg a konfigurációs adatok nincsenek közvetlenül átadva itt,
    # de a jövőben lehetőség lesz rá, ha bővítjük a konfigurációt YAML-ben.

    # Hardkódolt adatok a teszteléshez és az első lépésekhez
    # EZEKET KÉSŐBB BIZTONSÁGOSAN KELL KEZELNI (pl. Home Assistant secrets vagy config flow)!
    monitored_entity_id = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"
    db_host = "localhost" # Vagy core-mariadb, ha add-ont használsz és Dockerben futsz
    db_user = "homeassistant"
    db_password = "Pozsi1981"
    db_name = "homeassistant" # Általában ez a HA recorder adatbázis neve

    sensor = SiloPredictionSensor(
        hass,
        monitored_entity_id,
        db_host,
        db_user,
        db_password,
        db_name
    )

    async_add_entities([sensor], True)

class SiloPredictionSensor(SensorEntity):
    """Representation of a Silo Prediction Sensor."""

    _attr_name = "Silo 0kg Becsült Idő"
    _attr_device_class = SensorDeviceClass.TIMESTAMP # Időbélyeg típusú szenzor
    _attr_icon = "mdi:calendar-clock" # Óra ikon
    _attr_native_unit_of_measurement = None # Nincs egység, mivel időbélyeg
    _attr_should_poll = False # Mi magunk frissítjük az async_track_time_interval-lal

    def __init__(
        self,
        hass: HomeAssistant,
        monitored_entity_id: str,
        db_host: str,
        db_user: str,
        db_password: str,
        db_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._monitored_entity_id = monitored_entity_id
        self._db_host = db_host
        self._db_user = db_user
        self._db_password = db_password
        self._db_name = db_name

        self._attr_unique_id = f"{DOMAIN}_{monitored_entity_id.replace('.', '_')}_0kg_prediction"
        self._state = None # A szenzor állapota
        self._extra_state_attributes = {} # Extra attribútumok

        # Ütemezett frissítés beállítása
        async_track_time_interval(hass, self.async_update, SCAN_INTERVAL)


    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._extra_state_attributes

    async def async_update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        _LOGGER.debug(f"Starting prediction update for {self._monitored_entity_id}")
        data_df = None
        try:
            # 1. MariaDB Adatbázis Kapcsolódás és Adatgyűjtés
            # Az adatbázis lekérdezést aszinkron módon futtatjuk
            data_df = await self._hass.async_add_executor_job(
                self._fetch_and_process_data_from_db
            )

            if data_df is None or data_df.empty:
                _LOGGER.warning("No data retrieved from MariaDB or DataFrame is empty. Cannot perform prediction.")
                self._state = None
                self._extra_state_attributes["error"] = "No data for prediction"
                return

            # 2. Polinom Regressziós Logika Implementálása
            predicted_date_utc = self._perform_prediction(data_df)

            if predicted_date_utc:
                # 3. Időzóna konverzió helyi időre
                local_timezone = self._hass.config.time_zone
                if not local_timezone:
                    _LOGGER.warning("Home Assistant timezone not set. Using UTC for prediction display.")
                    local_timezone = "UTC" # Fallback to UTC

                try:
                    # Predicted date is UTC, convert to local HA timezone
                    # Ensure predicted_date_utc is timezone-aware UTC
                    if predicted_date_utc.tzinfo is None:
                        predicted_date_utc = predicted_date_utc.replace(tzinfo=ZoneInfo("UTC"))
                    
                    local_tz = ZoneInfo(local_timezone)
                    predicted_date_local = predicted_date_utc.astimezone(local_tz)

                    self._state = predicted_date_local # A szenzor állapota a helyi időzónás időbélyeg
                    self._extra_state_attributes["predicted_0kg_utc"] = predicted_date_utc.isoformat()
                    self._extra_state_attributes["last_run"] = datetime.now(ZoneInfo(local_timezone)).isoformat()
                    self._extra_state_attributes.pop("error", None) # Clear error if successful
                    _LOGGER.info(f"Prediction updated: {predicted_date_local.isoformat()}")

                except Exception as tz_err:
                    _LOGGER.error(f"Error converting timezone for prediction: {tz_err}")
                    self._state = predicted_date_utc.isoformat() # Fallback to UTC string
                    self._extra_state_attributes["error"] = f"Timezone conversion error: {tz_err}"
            else:
                self._state = None
                self._extra_state_attributes["error"] = "Prediction could not be made"
                _LOGGER.warning("Prediction could not be made for Silo Prediction sensor.")

        except mysql.connector.Error as db_err:
            _LOGGER.error(f"MariaDB connection or query error: {db_err}")
            self._state = None
            self._extra_state_attributes["error"] = f"DB error: {db_err}"
        except Exception as e:
            _LOGGER.error(f"Unexpected error during Silo Prediction update: {e}", exc_info=True)
            self._state = None
            self._extra_state_attributes["error"] = f"Unexpected error: {e}"

        # Értesítjük a Home Assistant-et, hogy az entitás állapota frissült
        self.async_write_ha_state()

    def _fetch_and_process_data_from_db(self) -> pd.DataFrame | None:
        """Fetches historical data from MariaDB and processes it using Pandas.
        This method runs in a separate executor as it involves synchronous DB calls.
        """
        _LOGGER.debug("Fetching data from MariaDB...")
        conn = None
        data = []
        try:
            conn = mysql.connector.connect(
                host=self._db_host,
                user=self._db_user,
                password=self._db_password,
                database=self._db_name
            )
            cursor = conn.cursor()

            # Lekérdezzük az entitás állapotait az elmúlt 30 napból
            # A timestamp oszlopot UTC-ben kapjuk vissza
            # Azért 30 nap, mert a polinom regresszióhoz kell elegendő múltbeli adat.
            start_date = (datetime.utcnow() - timedelta(days=30)).isoformat(timespec='seconds') + 'Z'

            query = f"""
            SELECT state, last_changed
            FROM states
            WHERE entity_id = '{self._monitored_entity_id}'
            AND last_changed >= '{start_date}'
            ORDER BY last_changed ASC;
            """
            cursor.execute(query)
            data = cursor.fetchall()
            _LOGGER.debug(f"Fetched {len(data)} rows from MariaDB.")

            if not data:
                return None

            # Pandas DataFrame létrehozása és feldolgozása
            df = pd.DataFrame(data, columns=['state', 'last_changed'])

            # Adattípus konverzió
            df['last_changed'] = pd.to_datetime(df['last_changed'])
            df['state'] = pd.to_numeric(df['state'], errors='coerce')

            # Hiányzó értékek és inkonzisztenciák kezelése
            df.dropna(subset=['state', 'last_changed'], inplace=True)
            df = df[df['state'] >= 0] # Csak pozitív súlyértékek

            if df.empty:
                _LOGGER.warning("DataFrame is empty after cleaning.")
                return None

            # Index beállítása és újra mintavételezés óránkénti átlagra
            df = df.set_index('last_changed')
            df_resampled = df['state'].resample('H').mean()
            df_resampled.dropna(inplace=True)

            if df_resampled.empty or len(df_resampled) < 2: # Need at least 2 points for regression
                _LOGGER.warning("Not enough data points after resampling for prediction.")
                return None

            _LOGGER.debug(f"Dataframe prepared with {len(df_resampled)} data points.")
            return df_resampled

        except mysql.connector.Error as err:
            _LOGGER.error(f"Database error during data fetch: {err}")
            return None
        except Exception as e:
            _LOGGER.error(f"Error in _fetch_and_process_data_from_db: {e}", exc_info=True)
            return None
        finally:
            if conn and conn.is_connected():
                conn.close()
                _LOGGER.debug("MariaDB connection closed.")

    def _perform_prediction(self, df_resampled: pd.Series) -> datetime | None:
        """Performs polynomial regression and predicts the 0kg date."""
        _LOGGER.debug("Performing prediction...")

        try:
            df_reg = pd.DataFrame({'timestamp': df_resampled.index, 'weight': df_resampled.values})

            min_timestamp = df_reg['timestamp'].min()
            df_reg['timestamp_numeric'] = (df_reg['timestamp'] - min_timestamp).dt.total_seconds()

            X = df_reg[['timestamp_numeric']]
            y = df_reg['weight']

            if len(X) < 2:
                _LOGGER.warning("Not enough data points for regression after numeric conversion.")
                return None

            # Polinom regresszió (Degree 2)
            degree = 2
            poly_model = make_pipeline(PolynomialFeatures(degree), LinearRegression())
            poly_model.fit(X, y)

            # Ellenőrizzük, hogy a súly csökkenő trendet mutat-e
            # Ha az utolsó súlyérték alacsonyabb, mint az első, akkor csökkenő a trend
            # Vagy ha a modell meredeksége negatív (az utolsó pontokban)
            # Egy egyszerű ellenőrzés: ha az aktuális súly 0, akkor már kifogyott
            if y.iloc[-1] <= 0:
                _LOGGER.info("Silo is already empty (weight <= 0).")
                return datetime.now(ZoneInfo("UTC")) # Return current time if already empty

            # Generálj jövőbeli időbélyegeket az előrejelzéshez (pl. a következő 60 nap)
            # A prediction horizon-t növeljük, hogy biztosan elérjük a 0-át, ha lassan fogy
            last_timestamp_numeric = X['timestamp_numeric'].max()
            future_timestamps_numeric = np.linspace(
                last_timestamp_numeric, last_timestamp_numeric + (60 * 24 * 3600), 500
            ).reshape(-1, 1)

            predicted_future_weights = poly_model.predict(future_timestamps_numeric)

            # Keressük meg az első pontot, ahol az előrejelzett súly <= 0
            predicted_0kg_numeric_time = None
            for i, weight in enumerate(predicted_future_weights):
                if weight <= 0:
                    predicted_0kg_numeric_time = future_timestamps_numeric[i][0]
                    break

            if predicted_0kg_numeric_time is not None:
                predicted_date_utc = min_timestamp + pd.to_timedelta(predicted_0kg_numeric_time, unit='s')
                # Győződjünk meg róla, hogy az előrejelzett dátum a jövőben van
                if predicted_date_utc < datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")):
                     _LOGGER.warning(f"Predicted 0kg date ({predicted_date_utc}) is in the past. Silo might be empty or prediction is unstable.")
                     return None # Vagy a legutóbbi adatpont ideje
                
                return predicted_date_utc.replace(tzinfo=ZoneInfo("UTC")) # Vissza UTC-ben

            _LOGGER.warning("No 0kg prediction found within the prediction horizon.")
            return None

        except Exception as e:
            _LOGGER.error(f"Error during prediction: {e}", exc_info=True)
            return None

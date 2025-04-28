import os
import json
from skyfield.api import load, wgs84
from datetime import datetime, timedelta, timezone

def get_tle(norad_id: int):
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}"
    try:
        satellites = load.tle_file(url)
        if not satellites:
            raise ValueError(f"Спутник {norad_id} не найден")
        return satellites[0]
    except Exception as e:
        raise RuntimeError(f"Ошибка загрузки TLE: {str(e)}")

def calculate_and_save_data(
    norad_id: int,
    observer_lat: float,
    observer_lon: float,
    start_time_utc: datetime,
    end_time_utc: datetime,
    step_seconds: int,
    passes_file: str,
    ephemeris_file: str,
    observer_elev: float,
    min_elevation: float
) -> None:
    # Загрузка данных
    satellite = get_tle(norad_id)
    ts = load.timescale()
    observer = wgs84.latlon(observer_lat, observer_lon, observer_elev)

    # Метаданные
    metadata = {
        "satellite": {
            "name": satellite.name.strip(),
            "norad_id": norad_id,
            "tle_source": f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}"
        },
        "observer": {
            "latitude": observer_lat,
            "longitude": observer_lon,
            "elevation_m": observer_elev
        },
        "calculation": {
            "start": start_time_utc.isoformat(),
            "end": end_time_utc.isoformat(),
            "step_seconds": step_seconds,
            "min_elevation_deg": min_elevation,
            "utc_calculated": datetime.now(timezone.utc).isoformat()
        }
    }

    # Расчет пролетов
    passes = []
    ephemeris = []
    current_pass = None
    pass_number = 0

    current_time = start_time_utc
    while current_time <= end_time_utc:
        t = ts.from_datetime(current_time)
        try:
            pos = satellite.at(t)
            subpoint = pos.subpoint()
            diff = pos - observer.at(t)
            alt, az, dist = diff.altaz()
           
            if alt.degrees >= min_elevation:
                if not current_pass:
                    pass_number += 1
                    current_pass = {
                        "pass_id": pass_number,
                        "start": current_time.isoformat(),
                        "end": current_time.isoformat(),
                        "max_elevation": round(alt.degrees, 2),
                        "events": []
                    }
                else:
                    current_pass["end"] = current_time.isoformat()
                    current_pass["max_elevation"] = max(
                        current_pass["max_elevation"],
                        round(alt.degrees, 2)
                    )

                # Эфемериды
                ephemeris_entry = {
                    "pass_id": pass_number,
                    "timestamp": current_time.isoformat(),
                    "geodetic": {
                        "latitude": round(subpoint.latitude.degrees, 6),
                        "longitude": round(subpoint.longitude.degrees, 6),
                        "altitude_km": round(subpoint.elevation.km, 3)
                    },
                    "topocentric": {
                        "elevation": round(alt.degrees, 3),
                        "azimuth": round(az.degrees, 3),
                        "distance_km": round(dist.km, 3)
                    }
                }
                ephemeris.append(ephemeris_entry)
                current_pass["events"].append(ephemeris_entry)
               
            elif current_pass:
                current_pass["duration_sec"] = round((
                    datetime.fromisoformat(current_pass["end"]) -
                    datetime.fromisoformat(current_pass["start"])
                ).total_seconds(), 1)
                passes.append(current_pass)
                current_pass = None

        except Exception as e:
            print(f"Ошибка для {current_time}: {str(e)}")
       
        current_time += timedelta(seconds=step_seconds)

    # Фиксация последнего пролета
    if current_pass:
        current_pass["duration_sec"] = round((
            datetime.fromisoformat(current_pass["end"]) -
            datetime.fromisoformat(current_pass["start"])
        ).total_seconds(), 1)
        passes.append(current_pass)

    # Сохранение в файлы
    with open(passes_file, 'w') as f:
        json.dump({
            "metadata": metadata,
            "statistics": {
                "total_passes": pass_number,
                "visible_time_total": sum(p["duration_sec"] for p in passes)
            },
            "passes": passes
        }, f, indent = 2, ensure_ascii = False)

    with open(ephemeris_file, 'w') as f:
        json.dump({
            "metadata": metadata,
            "ephemeris": ephemeris
        }, f, indent = 2, ensure_ascii = False)

# Для теста
if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    calculate_and_save_data(
        norad_id = 25544,  # МКС
        observer_lat = 55.7558,
        observer_lon = 37.6173,
        start_time_utc = datetime(2025, 4, 26, 0, 0, 0, tzinfo = timezone.utc),
        end_time_utc = datetime(2025, 4, 26, 10, 0, tzinfo = timezone.utc),
        step_seconds = 60,
        passes_file = "passes.json",
        ephemeris_file = "ephemeris.json",
        observer_elev = 150,
        min_elevation = 10.0
    )
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from skyfield.api import load, wgs84, EarthSatellite

def get_satellite_name(norad_id: int) -> str:
    try:
        # Запрос к API
        url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Парсинг сырого текста TLE
        raw_data = response.text
        if "404 Not Found" in raw_data:
            return f"SAT-{norad_id}"
            
        lines = raw_data.split('\n')
        if len(lines) >= 1:
            return lines[0].strip().split(' ')[0]
            
    except Exception as e:
        print(f"Ошибка: {str(e)}")
    
    return f"SAT-{norad_id}"

def calculate_and_save_data(
    tle_line1: str,
    tle_line2: str,
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
    # Инициализация объектов
    satellite = EarthSatellite(tle_line1, tle_line2)
    norad_id = satellite.model.satnum
    satellite_name = get_satellite_name(norad_id)
    observer = wgs84.latlon(observer_lat, observer_lon, observer_elev)
    ts = load.timescale()

    # Структуры данных
    common_metadata = {
        'satellite_name': satellite_name,
        'norad_id': norad_id,
        'observer': {
            'latitude': observer_lat,
            'longitude': observer_lon,
            'elevation_m': observer_elev
        },
        'calculation_parameters': {
            'start': start_time_utc.isoformat(),
            'end': end_time_utc.isoformat(),
            'step_seconds': step_seconds,
            'min_elevation_deg': min_elevation
        }
    }

    passes_data = []
    ephemeris_data = []
    pass_counter = 0
    current_pass = None
    current_time = start_time_utc

    while current_time <= end_time_utc:
        t = ts.from_datetime(current_time)
       
        try:
            # Расчет позиции
            sat_pos = satellite.at(t)
            distance_km = sat_pos.distance().km
            light_time_sec = distance_km / 299792.458
            t_obs = ts.from_datetime(current_time - timedelta(seconds = light_time_sec))
           
            observer_pos = observer.at(t_obs)
            difference = sat_pos - observer_pos
            alt, az, distance = difference.altaz()
           
            subpoint = sat_pos.subpoint()

        except Exception as e:
            print(f"Ошибка расчета для времени {current_time}: {str(e)}")
            current_time += timedelta(seconds = step_seconds)
            continue

        if alt.degrees >= min_elevation:
            if not current_pass:
                pass_counter += 1
                current_pass = {
                    'pass_id': pass_counter,
                    'start': current_time.isoformat(),
                    'end': current_time.isoformat(),
                    'max_elevation': alt.degrees,
                    'duration_sec': 0.0
                }
            else:
                current_pass['end'] = current_time.isoformat()
                current_pass['max_elevation'] = max(current_pass['max_elevation'], alt.degrees)

            # Добавление эфемерид
            ephemeris_entry = {
                'pass_id': pass_counter,
                'timestamp': current_time.isoformat(),
                'geodesic': {
                    'lat': round(subpoint.latitude.degrees, 6),
                    'lon': round(subpoint.longitude.degrees, 6),
                    'height_m': round(subpoint.elevation.m, 2)
                },
                'relative': {
                    'elevation': round(alt.degrees, 3),
                    'azimuth': round(az.degrees, 3),
                    'distance_km': round(distance.km, 3)
                }
            }
            ephemeris_data.append(ephemeris_entry)
           
        elif current_pass:
            # Фиксация пролета
            current_pass['duration_sec'] = (
                datetime.fromisoformat(current_pass['end']) -
                datetime.fromisoformat(current_pass['start'])
            ).total_seconds()
            passes_data.append(current_pass)
            current_pass = None

        current_time += timedelta(seconds = step_seconds)

    # Фиксация последнего пролета
    if current_pass:
        current_pass['duration_sec'] = (
            datetime.fromisoformat(current_pass['end']) -
            datetime.fromisoformat(current_pass['start'])
        ).total_seconds()
        passes_data.append(current_pass)

    passes_output = {
        'metadata': {
            **common_metadata,
            'total_passes': pass_counter
        },
        'passes': passes_data
    }

    ephemeris_output = {
        'metadata': common_metadata,
        'ephemeris': ephemeris_data
    }

    # Сохранение в файлы
    with open(passes_file, 'w', encoding = 'utf-8') as f:
        json.dump(passes_output, f, indent = 2, ensure_ascii = False)

    with open(ephemeris_file, 'w', encoding = 'utf-8') as f:
        json.dump(ephemeris_output, f, indent = 2, ensure_ascii = False)

# Для теста
if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    tle = [
        '1 25544U 98067A   21275.56033646  .00000952  00000-0  24223-4 0  9996',
        '2 25544  51.6444 320.1753 0004846 314.1101 142.4573 15.48918155293774'
    ]
   
    calculate_and_save_data(
        tle[0], tle[1],
        55.7522, 37.6156,
        datetime(2023, 10, 1, 0, 0, 0, tzinfo = timezone.utc),
        datetime(2023, 10, 1, 12, 0, 0, tzinfo = timezone.utc),
        10,
        'passes.json',
        'ephemeris.json',
        150,
        min_elevation = 10.0
    )
   
    print("Данные успешно сохранены в файлы:")
    print("- passes.json: информация о пролетах")
    print("- ephemeris.json: данные эфемерид")
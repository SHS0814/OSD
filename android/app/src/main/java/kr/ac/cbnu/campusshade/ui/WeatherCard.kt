package kr.ac.cbnu.campusshade.ui

import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.Sky
import kr.ac.cbnu.campusshade.WeatherIcon
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

/** The current-weather card (/api/weather) and the details it opens when tapped. */
class WeatherCard(private val activity: AppCompatActivity, private val binding: ActivityMainBinding) {
    // 현재 날씨 카드를 눌렀을 때 보여 줄 자세한 내용
    private var detail: String? = null

    init {
        binding.weatherCard.setOnClickListener { showDetail() }
    }

    /** Keeps the last weather shown when a refresh fails; hides the card if there was none. */
    fun onError() {
        if (detail == null) binding.weatherCard.visibility = View.GONE
    }

    fun show(root: JSONObject) {
        val weather = root.getJSONObject("weather")
        val temp = weather.optDouble("air_temp_c", Double.NaN)
        val cloud = weather.optDouble("cloud_fraction", Double.NaN)
        val altitude = root.optJSONObject("solar")?.optDouble("altitude", Double.NaN) ?: Double.NaN
        val sky = Sky.fromCloudFraction(cloud)
        binding.weatherIcon.setImageResource(
            when (WeatherIcon.of(sky, altitude)) {
                WeatherIcon.SUN -> R.drawable.ic_weather_sun
                WeatherIcon.MOON -> R.drawable.ic_weather_moon
                WeatherIcon.PARTLY_CLOUDY_DAY -> R.drawable.ic_weather_partly_day
                WeatherIcon.PARTLY_CLOUDY_NIGHT -> R.drawable.ic_weather_partly_night
                WeatherIcon.CLOUD -> R.drawable.ic_weather_cloud
            }
        )
        binding.weatherTemp.text = if (temp.isNaN()) activity.getString(R.string.weather_temp_unknown)
        else activity.getString(R.string.weather_temp, temp.roundToInt())
        binding.weatherSky.text = when (sky) {
            Sky.CLEAR -> activity.getString(R.string.weather_clear)
            Sky.PARTLY_CLOUDY -> activity.getString(R.string.weather_partly_cloudy)
            Sky.OVERCAST -> activity.getString(R.string.weather_overcast)
            null -> ""
        }
        val observedAt = weather.optString("observed_at").takeIf { it.isNotEmpty() }?.let {
            runCatching { OffsetDateTime.parse(it).atZoneSameInstant(SEOUL_ZONE).toLocalDateTime() }.getOrNull()
        }
        // latest: 지금은 아직 관측 전이라 가장 최근 관측값을 보여 준다.
        val showObserved = root.optBoolean("latest") && observedAt != null
        binding.weatherObserved.visibility = if (showObserved) View.VISIBLE else View.GONE
        if (showObserved) binding.weatherObserved.text = activity.getString(R.string.weather_observed, observedAt!!.format(MONTH_DAY_TIME))

        val humidity = weather.optDouble("relative_humidity", Double.NaN)
        val wind = weather.optDouble("wind_ms", Double.NaN)
        detail = listOfNotNull(
            observedAt?.let { activity.getString(R.string.weather_detail_station, weather.optString("station"), it.format(MONTH_DAY_TIME)) },
            temp.takeUnless { it.isNaN() }?.let { activity.getString(R.string.weather_detail_temp, it) },
            humidity.takeUnless { it.isNaN() }?.let { activity.getString(R.string.weather_detail_humidity, it) },
            wind.takeUnless { it.isNaN() }?.let { activity.getString(R.string.weather_detail_wind, it) },
            cloud.takeUnless { it.isNaN() }?.let { activity.getString(R.string.weather_detail_cloud, (it * 10).roundToInt()) },
        ).joinToString("\n")
        binding.weatherCard.visibility = View.VISIBLE
    }

    private fun showDetail() {
        val detail = detail ?: return
        AlertDialog.Builder(activity)
            .setTitle(R.string.weather_detail_title)
            .setMessage(detail)
            .setPositiveButton(R.string.weather_close, null)
            .show()
    }

    private companion object {
        val SEOUL_ZONE: ZoneId = ZoneId.of("Asia/Seoul")
        val MONTH_DAY_TIME: DateTimeFormatter = DateTimeFormatter.ofPattern("MM/dd HH:mm")
    }
}

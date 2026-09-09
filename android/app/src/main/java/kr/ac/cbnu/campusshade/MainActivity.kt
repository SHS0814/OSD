package kr.ac.cbnu.campusshade

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.SeekBar
import androidx.appcompat.app.AppCompatActivity
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.sources.GeoJsonSource
import java.io.IOException
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val client = OkHttpClient()
    private val handler = Handler(Looper.getMainLooper())
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var requestCall: Call? = null
    private var selectedMinutes = 14 * 60
    private val debounceRequest = Runnable { requestShadows() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MapLibre.getInstance(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.mapView.onCreate(savedInstanceState)

        setToCurrentTime(requestImmediately = false)
        configureTimeControls()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .build()
            mapLibreMap.setStyle(Style.Builder().fromUri(MapStyle.BASE_STYLE_URL)) { style ->
                mapStyle = style
                installDataLayers(style)
                requestBuildings()
                requestShadows()
            }
        }
    }

    private fun configureTimeControls() {
        binding.timeSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                selectedMinutes = START_MINUTES + progress
                updateTimeLabel()
                if (fromUser) {
                    handler.removeCallbacks(debounceRequest)
                    handler.postDelayed(debounceRequest, 400)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
        binding.nowButton.setOnClickListener { setToCurrentTime(requestImmediately = true) }
    }

    private fun setToCurrentTime(requestImmediately: Boolean) {
        val now = LocalDateTime.now(SEOUL_ZONE)
        selectedMinutes = (now.hour * 60 + now.minute).coerceIn(START_MINUTES, END_MINUTES)
        binding.timeSlider.progress = selectedMinutes - START_MINUTES
        updateTimeLabel()
        if (requestImmediately) requestShadows()
    }

    private fun updateTimeLabel() {
        binding.selectedTime.text = getString(
            R.string.selected_time,
            selectedMinutes / 60,
            selectedMinutes % 60,
        )
    }

    private fun installDataLayers(style: Style) {
        style.addSource(GeoJsonSource(MapStyle.BUILDING_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            FillLayer(MapStyle.BUILDING_LAYER, MapStyle.BUILDING_SOURCE).withProperties(
                fillColor(MapStyle.buildingFillColor),
                fillOpacity(MapStyle.BUILDING_OPACITY),
            )
        )
        style.addLayer(
            LineLayer(MapStyle.BUILDING_OUTLINE_LAYER, MapStyle.BUILDING_SOURCE).withProperties(
                lineColor(MapStyle.buildingStrokeColor),
                lineWidth(1.4f),
            )
        )
        style.addSource(GeoJsonSource(MapStyle.SHADOW_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            FillLayer(MapStyle.SHADOW_LAYER, MapStyle.SHADOW_SOURCE).withProperties(
                fillColor(MapStyle.shadowFillColor),
                fillOpacity(MapStyle.SHADOW_OPACITY),
            )
        )
    }

    private fun requestBuildings() {
        getJson("api/buildings") { payload ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.BUILDING_SOURCE)
                ?.setGeoJson(payload)
        }
    }

    private fun requestShadows() {
        if (mapStyle == null) return
        requestCall?.cancel()
        binding.statusText.text = getString(R.string.loading_shadows)
        val hour = selectedMinutes / 60
        val minute = selectedMinutes % 60
        val localDateTime = LocalDate.now(SEOUL_ZONE).atTime(hour, minute)
        val datetime = localDateTime.atZone(SEOUL_ZONE).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val url = (BuildConfig.API_BASE_URL + "api/shadows").toHttpUrl().newBuilder()
            .addQueryParameter("datetime", datetime)
            .addQueryParameter("lat", CAMPUS_CENTER.latitude.toString())
            .addQueryParameter("lon", CAMPUS_CENTER.longitude.toString())
            .build()
        val request = Request.Builder().url(url).build()
        requestCall = client.newCall(request).also { call ->
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, error: IOException) {
                    if (!call.isCanceled()) runOnUiThread {
                        binding.statusText.text = getString(R.string.network_error, error.localizedMessage)
                    }
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        val body = it.body?.string().orEmpty()
                        if (!it.isSuccessful) {
                            runOnUiThread { binding.statusText.text = getString(R.string.http_error, it.code) }
                            return
                        }
                        val root = JSONObject(body)
                        val shadows = root.getJSONObject("shadows").toString()
                        val altitude = root.getJSONObject("solar").getDouble("altitude")
                        runOnUiThread {
                            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.SHADOW_SOURCE)
                                ?.setGeoJson(shadows)
                            binding.statusText.text = getString(R.string.solar_altitude, altitude)
                        }
                    }
                }
            })
        }
    }

    private fun getJson(path: String, onSuccess: (String) -> Unit) {
        val request = Request.Builder().url(BuildConfig.API_BASE_URL + path).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                runOnUiThread { binding.statusText.text = getString(R.string.network_error, error.localizedMessage) }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val body = it.body?.string().orEmpty()
                    runOnUiThread {
                        if (it.isSuccessful) onSuccess(body)
                        else binding.statusText.text = getString(R.string.http_error, it.code)
                    }
                }
            }
        })
    }

    override fun onStart() { super.onStart(); binding.mapView.onStart() }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        requestCall?.cancel()
        handler.removeCallbacksAndMessages(null)
        binding.mapView.onDestroy()
        super.onDestroy()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.mapView.onSaveInstanceState(outState)
    }

    companion object {
        private val CAMPUS_CENTER = LatLng(36.6268, 127.4583)
        private val SEOUL_ZONE = ZoneId.of("Asia/Seoul")
        private const val START_MINUTES = 6 * 60
        private const val END_MINUTES = 20 * 60
        private const val EMPTY_FEATURE_COLLECTION =
            "{\"type\":\"FeatureCollection\",\"features\":[]}"
    }
}

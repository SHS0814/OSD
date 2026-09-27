package kr.ac.cbnu.campusshade

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.graphics.ColorUtils
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.coalesce
import org.maplibre.android.style.expressions.Expression.color
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.switchCase
import org.maplibre.android.style.expressions.Expression.typeOf
import org.maplibre.android.style.layers.FillExtrusionLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.Layer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionBase
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionHeight
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionOpacity
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.layers.PropertyFactory.rasterOpacity
import org.maplibre.android.style.layers.PropertyFactory.rasterResampling
import org.maplibre.android.style.layers.PropertyFactory.visibility
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.android.style.sources.ImageSource
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
    private var shadowCall: Call? = null
    private var microclimateCall: Call? = null
    private var selectedMinutes = 14 * 60
    private var is3d = true
    private var showHeatmap = true

    // Weather observations only reach yesterday, so shadows and felt temperature
    // are both shown for the latest date the server has weather for.
    private var dataDate: LocalDate = LocalDate.now(SEOUL_ZONE).minusDays(1)
    private val debounceRequest = Runnable { requestForSelectedTime() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MapLibre.getInstance(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        // Android 15+ draws apps edge to edge; keep the title and controls clear of
        // the status and navigation bars.
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        binding.mapView.onCreate(savedInstanceState)

        setToCurrentTime(requestImmediately = false)
        configureControls()
        buildLegend()
        updateDataDateLabel()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .tilt(MapStyle.TILT_3D)
                .build()
            mapLibreMap.setStyle(Style.Builder().fromUri(MapStyle.BASE_STYLE_URL)) { style ->
                mapStyle = style
                installDataLayers(style)
                requestBuildings()
                requestDataDateThenRefresh()
            }
        }
    }

    private fun configureControls() {
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
        binding.viewModeButton.setOnClickListener { toggleViewMode() }
        binding.layerModeButton.setOnClickListener { toggleLayerMode() }
        updateViewModeButton()
        updateLayerMode()
    }

    private fun toggleViewMode() {
        is3d = !is3d
        val tilt = if (is3d) MapStyle.TILT_3D else 0.0
        map?.animateCamera(CameraUpdateFactory.tiltTo(tilt), 600)
        updateViewModeButton()
    }

    private fun updateViewModeButton() {
        binding.viewModeButton.setText(if (is3d) R.string.view_2d else R.string.view_3d)
    }

    // The heatmap already accounts for shade, so it replaces the shadow layer
    // instead of being drawn on top of it.
    private fun toggleLayerMode() {
        showHeatmap = !showHeatmap
        updateLayerMode()
        requestForSelectedTime()
    }

    private fun updateLayerMode() {
        binding.layerModeButton.setText(if (showHeatmap) R.string.show_shadows else R.string.show_heatmap)
        binding.legend.visibility = if (showHeatmap) android.view.View.VISIBLE else android.view.View.GONE
        mapStyle?.let { style ->
            style.getLayer(MapStyle.HEATMAP_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.VISIBLE else Property.NONE))
            style.getLayer(MapStyle.SHADOW_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.NONE else Property.VISIBLE))
        }
    }

    private fun buildLegend() {
        val density = resources.displayMetrics.density
        UtciPalette.legend.forEach { (label, value) ->
            val background = UtciPalette.colorFor(value)
            binding.legend.addView(
                TextView(this).apply {
                    text = label
                    textSize = 10f
                    gravity = Gravity.CENTER
                    setBackgroundColor(background)
                    setTextColor(
                        if (ColorUtils.calculateLuminance(background) > 0.45) 0xFF1F2937.toInt()
                        else 0xFFFFFFFF.toInt()
                    )
                    setPadding(0, (3 * density).toInt(), 0, (3 * density).toInt())
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
            )
        }
    }

    private fun setToCurrentTime(requestImmediately: Boolean) {
        val now = LocalDateTime.now(SEOUL_ZONE)
        selectedMinutes = (now.hour * 60 + now.minute).coerceIn(START_MINUTES, END_MINUTES)
        binding.timeSlider.progress = selectedMinutes - START_MINUTES
        updateTimeLabel()
        if (requestImmediately) requestForSelectedTime()
    }

    private fun updateTimeLabel() {
        binding.selectedTime.text = getString(
            R.string.selected_time,
            selectedMinutes / 60,
            selectedMinutes % 60,
        )
    }

    private fun updateDataDateLabel() {
        binding.dataDateText.text = getString(
            R.string.data_date,
            dataDate.format(DateTimeFormatter.ofPattern("yyyy-MM-dd")),
        )
    }

    private fun installDataLayers(style: Style) {
        // 그림자는 바닥에 깔고 건물은 그 위로 세운다. 둘 다 기본 지도의 라벨 아래에 둔다.
        // 체감온도 히트맵은 첫 응답에서 그림자 아래에 추가한다.
        style.addSource(GeoJsonSource(MapStyle.SHADOW_SOURCE, EMPTY_FEATURE_COLLECTION))
        addBelowLabels(
            style,
            FillLayer(MapStyle.SHADOW_LAYER, MapStyle.SHADOW_SOURCE).withProperties(
                fillColor(MapStyle.shadowFillColor),
                fillOpacity(MapStyle.SHADOW_OPACITY),
            )
        )
        val hasHeight = eq(typeOf(get("height_m")), literal("number"))
        style.addSource(GeoJsonSource(MapStyle.BUILDING_SOURCE, EMPTY_FEATURE_COLLECTION))
        addBelowLabels(
            style,
            FillExtrusionLayer(MapStyle.BUILDING_LAYER, MapStyle.BUILDING_SOURCE).withProperties(
                fillExtrusionHeight(coalesce(get("height_m"), literal(MapStyle.UNKNOWN_HEIGHT_M))),
                fillExtrusionBase(0f),
                fillExtrusionColor(
                    switchCase(
                        hasHeight, color(MapStyle.buildingFillColor),
                        color(MapStyle.unknownHeightFillColor),
                    )
                ),
                fillExtrusionOpacity(MapStyle.BUILDING_OPACITY),
            )
        )
        updateLayerMode()
    }

    private fun addBelowLabels(style: Style, layer: Layer) {
        val firstLabel = style.layers.firstOrNull { it is SymbolLayer }
        if (firstLabel == null) style.addLayer(layer) else style.addLayerBelow(layer, firstLabel.id)
    }

    private fun showHeatmap(heatmap: UtciHeatmap) {
        val style = mapStyle ?: return
        val source = style.getSourceAs<ImageSource>(MapStyle.HEATMAP_SOURCE)
        if (source == null) {
            style.addSource(ImageSource(MapStyle.HEATMAP_SOURCE, heatmap.quad, heatmap.bitmap))
            style.addLayerBelow(
                RasterLayer(MapStyle.HEATMAP_LAYER, MapStyle.HEATMAP_SOURCE).withProperties(
                    rasterOpacity(MapStyle.HEATMAP_OPACITY),
                    rasterResampling(Property.RASTER_RESAMPLING_LINEAR),
                ),
                MapStyle.SHADOW_LAYER,
            )
            updateLayerMode()
        } else {
            source.setCoordinates(heatmap.quad)
            source.setImage(heatmap.bitmap)
        }
    }

    private fun requestBuildings() {
        fetchJson(apiUrl("api/buildings").build(), null) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.BUILDING_SOURCE)
                ?.setGeoJson(root.toString())
        }
    }

    private fun requestDataDateThenRefresh() {
        val yesterday = LocalDate.now(SEOUL_ZONE).minusDays(1)
        fetchJson(
            apiUrl("api/weather/period").build(),
            null,
            onError = { requestForSelectedTime() },
        ) { root ->
            val latest = LocalDate.parse(root.getString("latest_full_date"))
            dataDate = if (latest.isBefore(yesterday)) latest else yesterday
            updateDataDateLabel()
            requestForSelectedTime()
        }
    }

    private fun requestForSelectedTime() {
        if (mapStyle == null) return
        if (showHeatmap) requestMicroclimate() else requestShadows()
    }

    private fun selectedDateTime(): String =
        dataDate.atTime(selectedMinutes / 60, selectedMinutes % 60)
            .atZone(SEOUL_ZONE)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)

    private fun requestShadows() {
        shadowCall?.cancel()
        binding.statusText.text = getString(R.string.loading_shadows)
        val url = apiUrl("api/shadows")
            .addQueryParameter("datetime", selectedDateTime())
            .addQueryParameter("lat", CAMPUS_CENTER.latitude.toString())
            .addQueryParameter("lon", CAMPUS_CENTER.longitude.toString())
            .build()
        shadowCall = fetchJson(url, shadowCall) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.SHADOW_SOURCE)
                ?.setGeoJson(root.getJSONObject("shadows").toString())
            val altitude = root.getJSONObject("solar").getDouble("altitude")
            binding.statusText.text = getString(R.string.solar_altitude, altitude)
        }
    }

    private fun requestMicroclimate() {
        microclimateCall?.cancel()
        binding.statusText.text = getString(R.string.loading_microclimate)
        val url = apiUrl("api/microclimate")
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        microclimateCall = fetchJson(url, microclimateCall, parse = UtciHeatmap::fromResponse) { root, heatmap ->
            showHeatmap(heatmap)
            val summary = root.getJSONObject("summary")
            val airTemp = root.getJSONObject("weather").getDouble("air_temp_c")
            val sunUp = root.getJSONObject("solar").getDouble("altitude") > 0
            binding.statusText.text = if (sunUp) {
                getString(
                    R.string.utci_summary,
                    airTemp,
                    summary.getDouble("utci_min"),
                    summary.getDouble("utci_max"),
                    summary.getDouble("utci_mean"),
                )
            } else {
                getString(R.string.utci_night, airTemp, summary.getDouble("utci_mean"))
            }
        }
    }

    private fun apiUrl(path: String): HttpUrl.Builder =
        (BuildConfig.API_BASE_URL + path).toHttpUrl().newBuilder()

    private fun fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: (() -> Unit)? = null,
        onSuccess: (JSONObject) -> Unit,
    ): Call = fetchJson(url, previous, onError, parse = { }) { root, _ -> onSuccess(root) }

    /**
     * GET [url] and hand the parsed body to [onSuccess] on the UI thread. [parse]
     * runs on the network thread first, for work such as building a bitmap.
     */
    private fun <T> fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: (() -> Unit)? = null,
        parse: (JSONObject) -> T,
        onSuccess: (JSONObject, T) -> Unit,
    ): Call {
        previous?.cancel()
        val call = client.newCall(Request.Builder().url(url).build())
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (call.isCanceled()) return
                runOnUiThread {
                    binding.statusText.text = getString(R.string.network_error, error.localizedMessage)
                    onError?.invoke()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        runOnUiThread {
                            binding.statusText.text = getString(R.string.http_error, it.code)
                            onError?.invoke()
                        }
                        return
                    }
                    val root = JSONObject(it.body?.string().orEmpty())
                    val parsed = parse(root)
                    if (!call.isCanceled()) runOnUiThread { onSuccess(root, parsed) }
                }
            }
        })
        return call
    }

    override fun onStart() { super.onStart(); binding.mapView.onStart() }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        shadowCall?.cancel()
        microclimateCall?.cancel()
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

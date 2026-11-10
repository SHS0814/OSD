package kr.ac.cbnu.campusshade

import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import kr.ac.cbnu.campusshade.map.MapLayers
import kr.ac.cbnu.campusshade.ui.Legend
import kr.ac.cbnu.campusshade.ui.MapSettingsSheet
import kr.ac.cbnu.campusshade.ui.TimeSheet
import okhttp3.Call
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The one screen. It keeps what has been chosen (time, layers, route ends,
 * where you are) and asks the API; the map layers (map/) draw the answers and
 * the panels (ui/) show them and report what the user picks.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var api: ApiClient
    // 시각 선택과 지도 설정은 바텀시트에 담는다. 한 번 만들어 두고 다시 연다.
    private lateinit var timeSheet: TimeSheet
    private lateinit var mapSettings: MapSettingsSheet
    private lateinit var legend: Legend
    private val handler = Handler(Looper.getMainLooper())
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var layers: MapLayers? = null
    private var shadowCall: Call? = null
    private var microclimateCall: Call? = null
    private var selectedMinutes = 14 * 60
    // 시각 카드의 "현재 시각"/"선택 시각": 날짜나 시각을 직접 고르면 false
    private var followingNow = true
    private var is3d = true
    private var showHeatmap = true

    private var dataDate: LocalDate = LocalDate.now(SEOUL_ZONE)
    private val debounceRequest = Runnable { requestForSelectedTime() }

    override fun onCreate(savedInstanceState: Bundle?) {
        // 지도는 상태바·내비게이션바 아래까지 그리고, 밝은 지도 위라 바 아이콘은 어둡게 둔다.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        MapLibre.getInstance(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        // 지도는 화면 끝까지 채우고, 떠 있는 컨트롤만 시스템 바와 화면 컷아웃을 피한다.
        ViewCompat.setOnApplyWindowInsetsListener(binding.overlay) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        binding.mapView.onCreate(savedInstanceState)

        api = ApiClient(this) { binding.statusText.text = it }
        timeSheet = TimeSheet(this, binding)
        mapSettings = MapSettingsSheet(this)
        legend = Legend(binding.legend)

        setToCurrentTime(requestImmediately = false)
        configureControls()
        updateDataDateLabel()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .tilt(MapStyle.TILT_3D)
                .build()
            // 저작권 표시는 아래 카드에 모아 둔다.
            mapLibreMap.uiSettings.isLogoEnabled = false
            mapLibreMap.uiSettings.isAttributionEnabled = false
            mapLibreMap.setStyle(Style.Builder().fromUri(MapStyle.BASE_STYLE_URL)) { style ->
                mapStyle = style
                installDataLayers(style)
                requestBuildings()
                requestForSelectedTime()
            }
        }
    }

    private fun configureControls() {
        timeSheet.onSlide = { progress, fromUser ->
            selectedMinutes = START_MINUTES + progress
            if (fromUser) followingNow = false
            updateTimeLabel()
            if (fromUser) {
                handler.removeCallbacks(debounceRequest)
                handler.postDelayed(debounceRequest, 400)
            }
        }
        timeSheet.onNow = {
            dataDate = LocalDate.now(SEOUL_ZONE)
            setToCurrentTime(requestImmediately = true)
            updateDataDateLabel()
        }

        binding.mapSettingsButton.setOnClickListener { mapSettings.show() }
        mapSettings.on3dPicked = { if (it != is3d) toggleViewMode() }
        mapSettings.onHeatmapPicked = { if (it != showHeatmap) toggleLayerMode() }
        updateViewModeButton()
        updateLayerMode()
    }

    private fun toggleViewMode() {
        is3d = !is3d
        val tilt = if (is3d) MapStyle.TILT_3D else 0.0
        map?.animateCamera(CameraUpdateFactory.tiltTo(tilt), 600)
        updateViewModeButton()
    }

    private fun updateViewModeButton() = mapSettings.show3d(is3d)

    // The heatmap already accounts for shade, so it replaces the shadow layer
    // instead of being drawn on top of it.
    private fun toggleLayerMode() {
        showHeatmap = !showHeatmap
        updateLayerMode()
        requestForSelectedTime()
    }

    private fun updateLayerMode() {
        mapSettings.showHeatmap(showHeatmap)
        legend.setVisible(showHeatmap)
        layers?.let {
            it.heatmap.setVisible(showHeatmap)
            it.shadows.setVisible(!showHeatmap)
        }
    }

    private fun setToCurrentTime(requestImmediately: Boolean) {
        val now = LocalDateTime.now(SEOUL_ZONE)
        selectedMinutes = (now.hour * 60 + now.minute).coerceIn(START_MINUTES, END_MINUTES)
        followingNow = true
        timeSheet.setProgress(selectedMinutes - START_MINUTES)
        updateTimeLabel()
        if (requestImmediately) requestForSelectedTime()
    }

    private fun updateTimeLabel() {
        timeSheet.showSelectedTime(selectedMinutes)
        updateTimeCard()
    }

    private fun updateTimeCard() {
        timeSheet.showCard(followingNow, selectedMinutes, dataDate, LocalDate.now(SEOUL_ZONE))
    }

    private fun updateDataDateLabel() = updateTimeCard()

    // ---- 지도 데이터 ----

    private fun installDataLayers(style: Style) {
        layers = MapLayers(style, this)
        updateLayerMode()
    }

    private fun showHeatmap(heatmap: UtciHeatmap) {
        val layers = layers ?: return
        if (layers.heatmap.show(heatmap)) {
            updateLayerMode()
        } else {
            updateLayerMode()
        }
    }

    private fun requestBuildings() {
        api.fetchJson(api.url("api/buildings").build(), null) { root ->
            layers?.buildings?.show(root.toString())
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
        val url = api.url("api/shadows")
            .addQueryParameter("datetime", selectedDateTime())
            .addQueryParameter("lat", CAMPUS_CENTER.latitude.toString())
            .addQueryParameter("lon", CAMPUS_CENTER.longitude.toString())
            .build()
        shadowCall = api.fetchJson(url, shadowCall) { root ->
            layers?.shadows?.show(root.getJSONObject("shadows").toString())
            val altitude = root.getJSONObject("solar").getDouble("altitude")
            binding.statusText.text = getString(R.string.solar_altitude, altitude)
        }
    }

    private fun requestMicroclimate() {
        microclimateCall?.cancel()
        binding.statusText.text = getString(R.string.loading_microclimate)
        val url = api.url("api/microclimate")
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        microclimateCall = api.fetchJson(
            url,
            microclimateCall,
            onError = { code ->
                if (code == 404) layers?.heatmap?.setVisible(false)
            },
            parse = UtciHeatmap::fromResponse,
        ) { root, heatmap ->
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

    override fun onStart() {
        super.onStart()
        binding.mapView.onStart()
    }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        shadowCall?.cancel()
        microclimateCall?.cancel()
        timeSheet.dismiss()
        mapSettings.dismiss()
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
    }
}

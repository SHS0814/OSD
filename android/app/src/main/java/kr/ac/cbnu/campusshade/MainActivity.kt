package kr.ac.cbnu.campusshade

import android.Manifest
import android.annotation.SuppressLint
import android.app.DatePickerDialog
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.PointF
import android.graphics.RectF
import android.location.Location
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.core.graphics.drawable.toBitmap
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.widget.doAfterTextChanged
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.chip.Chip
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import kr.ac.cbnu.campusshade.databinding.ItemInfoRowBinding
import kr.ac.cbnu.campusshade.databinding.SheetSensorBinding
import kr.ac.cbnu.campusshade.databinding.SheetMapSettingsBinding
import kr.ac.cbnu.campusshade.databinding.SheetTimeBinding
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
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.engine.LocationEngineCallback
import org.maplibre.android.location.engine.LocationEngineRequest
import org.maplibre.android.location.engine.LocationEngineResult
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.location.modes.RenderMode
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.all
import org.maplibre.android.style.expressions.Expression.coalesce
import org.maplibre.android.style.expressions.Expression.color
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.interpolate
import org.maplibre.android.style.expressions.Expression.linear
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.match
import org.maplibre.android.style.expressions.Expression.stop
import org.maplibre.android.style.expressions.Expression.sum
import org.maplibre.android.style.expressions.Expression.switchCase
import org.maplibre.android.style.expressions.Expression.typeOf
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.FillExtrusionLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.Layer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circlePitchAlignment
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionBase
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionHeight
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionOpacity
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.layers.PropertyFactory.iconAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.iconIgnorePlacement
import org.maplibre.android.style.layers.PropertyFactory.iconImage
import org.maplibre.android.style.layers.PropertyFactory.iconOpacity
import org.maplibre.android.style.layers.PropertyFactory.iconPitchAlignment
import org.maplibre.android.style.layers.PropertyFactory.iconRotate
import org.maplibre.android.style.layers.PropertyFactory.iconRotationAlignment
import org.maplibre.android.style.layers.PropertyFactory.iconSize
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.layers.PropertyFactory.rasterOpacity
import org.maplibre.android.style.layers.PropertyFactory.rasterResampling
import org.maplibre.android.style.layers.PropertyFactory.textAnchor
import org.maplibre.android.style.layers.PropertyFactory.textColor
import org.maplibre.android.style.layers.PropertyFactory.textField
import org.maplibre.android.style.layers.PropertyFactory.textFont
import org.maplibre.android.style.layers.PropertyFactory.textHaloColor
import org.maplibre.android.style.layers.PropertyFactory.textHaloWidth
import org.maplibre.android.style.layers.PropertyFactory.textOffset
import org.maplibre.android.style.layers.PropertyFactory.textSize
import org.maplibre.android.style.layers.PropertyFactory.visibility
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.android.style.sources.ImageSource
import org.maplibre.android.style.sources.RasterSource
import org.maplibre.android.style.sources.TileSet
import java.io.IOException
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    // 시각 선택과 지도 설정은 바텀시트에 담는다. 한 번 만들어 두고 다시 연다.
    private lateinit var timeSheet: SheetTimeBinding
    private lateinit var timeSheetDialog: BottomSheetDialog
    private lateinit var mapSettings: SheetMapSettingsBinding
    private lateinit var mapSettingsDialog: BottomSheetDialog
    private val client = OkHttpClient()
    private val handler = Handler(Looper.getMainLooper())
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var shadowCall: Call? = null
    private var microclimateCall: Call? = null
    private var weatherCall: Call? = null
    private var selectedMinutes = 14 * 60
    // 시각 카드의 "현재 시각"/"선택 시각": 날짜나 시각을 직접 고르면 false
    private var followingNow = true
    private var is3d = true
    private var showHeatmap = true
    private var showSatellite = true
    private var showWind = false
    private var windCall: Call? = null
    // 센서 위치: 기본으로 보이고, 누르면 정보 시트를 연다.
    private var showSensors = true
    private var sensors: List<SensorSite> = emptyList()
    private lateinit var sensorSheet: SheetSensorBinding
    private lateinit var sensorSheetDialog: BottomSheetDialog

    // 내 위치 체감온도: '지금'의 UTCI 격자와 최근 위치
    private var feltGrid: UtciGrid? = null
    private var feltCall: Call? = null
    private var myLocation: Location? = null
    private var locationUpdatesOn = false
    private val locationCallback = object : LocationEngineCallback<LocationEngineResult> {
        override fun onSuccess(result: LocationEngineResult?) {
            result?.lastLocation?.let { myLocation = it; updateFeltHere() }
        }
        override fun onFailure(exception: Exception) = Unit
    }

    // 건물 검색
    private var buildings: List<Building> = emptyList()
    private var selectedZone = BuildingSearch.ALL
    private var selectedBuilding: Building? = null
    private var suppressSearchWatcher = false
    private lateinit var buildingAdapter: BuildingAdapter
    private val closeOverlaysOnBack = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            if (binding.searchResultsCard.visibility == View.VISIBLE) hideSearchResults() else hideSelection()
        }
    }

    // 길찾기: 출발지·도착지(검색한 건물 또는 지도에서 길게 누른 곳)
    private var routeStart: Place? = null
    private var routeEnd: Place? = null
    private var routeCall: Call? = null
    // 출발·도착 핀 끌기: 누른 핀("start"/"end"), 손가락과 핀 중심의 차이, 끌기 전 자리
    private var dragRole: String? = null
    private var dragOffset = PointF()
    private var dragDown = PointF()
    private var dragMoved = false
    private var dragOriginal: Place? = null

    // 현재 날씨 카드를 눌렀을 때 보여 줄 자세한 내용
    private var weatherDetail: String? = null

    private val locationPermissionRequest =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
            if (granted.values.any { it }) {
                showMyLocation()
            } else {
                Toast.makeText(this, R.string.location_denied, Toast.LENGTH_LONG).show()
            }
        }

    // Shadows and felt temperature are shown for today when the server keeps its
    // weather current (API허브), otherwise for the last fully observed day.
    private var dataDate: LocalDate = LocalDate.now(SEOUL_ZONE)
    // The date "현재 시각" returns to, and the range the date picker allows;
    // both come from /api/weather/period.
    private var defaultDate: LocalDate = dataDate
    private var firstDate: LocalDate? = null
    private var latestObservation: LocalDateTime? = null
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

        timeSheet = SheetTimeBinding.inflate(layoutInflater)
        timeSheetDialog = BottomSheetDialog(this).apply { setContentView(timeSheet.root) }
        mapSettings = SheetMapSettingsBinding.inflate(layoutInflater)
        mapSettingsDialog = BottomSheetDialog(this).apply { setContentView(mapSettings.root) }
        sensorSheet = SheetSensorBinding.inflate(layoutInflater)
        sensorSheetDialog = BottomSheetDialog(this).apply { setContentView(sensorSheet.root) }
        onBackPressedDispatcher.addCallback(this, closeOverlaysOnBack)

        setToCurrentTime(requestImmediately = false)
        configureControls()
        configureSearch()
        buildLegend()
        updateDataDateLabel()
        requestWeather()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .tilt(MapStyle.TILT_3D)
                .build()
            // 나침반은 직접 그린 버튼을 쓰고, 저작권 표시는 아래 카드에 모아 둔다.
            mapLibreMap.uiSettings.isCompassEnabled = false
            mapLibreMap.uiSettings.isLogoEnabled = false
            mapLibreMap.uiSettings.isAttributionEnabled = false
            mapLibreMap.addOnMapLongClickListener { point -> hideSearchResults(); pickRoutePoint(point); true }
            mapLibreMap.addOnMapClickListener { point -> onMapTapped(point) }
            configurePinDragging()
            mapLibreMap.addOnCameraMoveListener { updateCompass() }
            mapLibreMap.addOnCameraIdleListener { updateCompass() }
            mapLibreMap.setStyle(Style.Builder().fromUri(MapStyle.BASE_STYLE_URL)) { style ->
                mapStyle = style
                installDataLayers(style)
                requestBuildings()
                requestSensors()
                // 권한을 이미 받았다면 내 위치 점과 체감 효과를 바로 켠다 (카메라는 그대로).
                activateLocation()
                requestDataDateThenRefresh()
            }
        }
    }

    private fun configureControls() {
        timeSheet.timeSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                selectedMinutes = START_MINUTES + progress
                if (fromUser) followingNow = false
                updateTimeLabel()
                if (fromUser) {
                    handler.removeCallbacks(debounceRequest)
                    handler.postDelayed(debounceRequest, 400)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
        timeSheet.nowButton.setOnClickListener {
            dataDate = defaultDate
            setToCurrentTime(requestImmediately = true)
            updateDataDateLabel()
            requestWeather()
        }
        timeSheet.dateButton.setOnClickListener { pickDate() }
        binding.timeCard.setOnClickListener { timeSheetDialog.show() }

        binding.mapSettingsButton.setOnClickListener { mapSettingsDialog.show() }
        mapSettings.viewModeGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked && (id == R.id.viewMode3d) != is3d) toggleViewMode()
        }
        mapSettings.baseMapGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked && (id == R.id.baseMapSatellite) != showSatellite) toggleBaseMap()
        }
        mapSettings.layerModeGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked && (id == R.id.layerHeatmap) != showHeatmap) toggleLayerMode()
        }
        mapSettings.windGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked && (id == R.id.windOn) != showWind) toggleWind()
        }
        mapSettings.sensorGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked && (id == R.id.sensorsOn) != showSensors) { showSensors = !showSensors; updateSensors() }
        }

        binding.compassButton.setOnClickListener {
            map?.animateCamera(CameraUpdateFactory.bearingTo(0.0), 400)
        }
        binding.myLocationButton.setOnClickListener { onMyLocationClicked() }
        binding.weatherCard.setOnClickListener { showWeatherDetail() }

        binding.routeFromButton.setOnClickListener { useSelectedBuildingAsRouteEnd(start = true) }
        binding.routeToButton.setOnClickListener { useSelectedBuildingAsRouteEnd(start = false) }
        binding.selectionCloseButton.setOnClickListener { hideSelection() }
        binding.clearRouteButton.setOnClickListener { clearRoute() }
        updateViewModeButton()
        updateLayerMode()
        updateBaseMapButton()
        updateWindButton()
        updateSensors()
    }

    private fun toggleViewMode() {
        is3d = !is3d
        val tilt = if (is3d) MapStyle.TILT_3D else 0.0
        map?.animateCamera(CameraUpdateFactory.tiltTo(tilt), 600)
        updateViewModeButton()
    }

    private fun updateViewModeButton() {
        mapSettings.viewModeGroup.check(if (is3d) R.id.viewMode3d else R.id.viewMode2d)
    }

    // The heatmap already accounts for shade, so it replaces the shadow layer
    // instead of being drawn on top of it.
    private fun toggleLayerMode() {
        showHeatmap = !showHeatmap
        updateLayerMode()
        requestForSelectedTime()
    }

    private fun updateLayerMode() {
        mapSettings.layerModeGroup.check(if (showHeatmap) R.id.layerHeatmap else R.id.layerShadow)
        binding.legend.visibility = if (showHeatmap) View.VISIBLE else View.GONE
        mapStyle?.let { style ->
            style.getLayer(MapStyle.HEATMAP_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.VISIBLE else Property.NONE))
            style.getLayer(MapStyle.SHADOW_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.NONE else Property.VISIBLE))
        }
    }

    private fun toggleBaseMap() {
        showSatellite = !showSatellite
        updateBaseMap()
    }

    private fun updateBaseMapButton() {
        mapSettings.baseMapGroup.check(if (showSatellite) R.id.baseMapSatellite else R.id.baseMapNormal)
    }

    // 위성사진은 기본 지도 위, 라벨 아래에 깔아서 도로명·건물명은 그대로 보이게 한다.
    private fun updateBaseMap() {
        updateBaseMapButton()
        mapStyle?.getLayer(MapStyle.SATELLITE_LAYER)
            ?.setProperties(visibility(if (showSatellite) Property.VISIBLE else Property.NONE))
        mapStyle?.getLayer(MapStyle.HEATMAP_LAYER)?.setProperties(
            rasterOpacity(if (showSatellite) MapStyle.HEATMAP_OPACITY_ON_SATELLITE else MapStyle.HEATMAP_OPACITY)
        )
    }

    private fun toggleWind() {
        showWind = !showWind
        updateWindButton()
        if (showWind) {
            requestWind()
        } else {
            windCall?.cancel()
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.WIND_SOURCE)?.setGeoJson(EMPTY_FEATURE_COLLECTION)
            binding.windText.visibility = View.GONE
        }
    }

    private fun updateWindButton() {
        mapSettings.windGroup.check(if (showWind) R.id.windOn else R.id.windOff)
    }

    private fun updateSensors() {
        mapSettings.sensorGroup.check(if (showSensors) R.id.sensorsOn else R.id.sensorsOff)
        val visibility = visibility(if (showSensors) Property.VISIBLE else Property.NONE)
        mapStyle?.getLayer(MapStyle.SENSOR_LAYER)?.setProperties(visibility)
        mapStyle?.getLayer(MapStyle.SENSOR_LABEL_LAYER)?.setProperties(visibility)
        if (!showSensors) sensorSheetDialog.dismiss()
    }

    // 지도가 돌아간 만큼 바늘을 반대로 돌려 늘 북쪽을 가리키게 한다.
    private fun updateCompass() {
        val bearing = map?.cameraPosition?.bearing ?: 0.0
        binding.compassNeedle.rotation = -bearing.toFloat()
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

    private fun pickDate() {
        DatePickerDialog(
            this,
            { _, year, month, day ->
                dataDate = LocalDate.of(year, month + 1, day)
                followingNow = false
                updateDataDateLabel()
                requestForSelectedTime()
            },
            dataDate.year,
            dataDate.monthValue - 1,
            dataDate.dayOfMonth,
        ).apply {
            firstDate?.let { datePicker.minDate = it.toEpochMillis() }
            datePicker.maxDate = defaultDate.toEpochMillis()
        }.show()
    }

    private fun LocalDate.toEpochMillis(): Long = atStartOfDay(SEOUL_ZONE).toInstant().toEpochMilli()

    private fun setToCurrentTime(requestImmediately: Boolean) {
        val now = LocalDateTime.now(SEOUL_ZONE)
        selectedMinutes = (now.hour * 60 + now.minute).coerceIn(START_MINUTES, END_MINUTES)
        followingNow = true
        timeSheet.timeSlider.progress = selectedMinutes - START_MINUTES
        updateTimeLabel()
        if (requestImmediately) requestForSelectedTime()
    }

    private fun updateTimeLabel() {
        timeSheet.selectedTime.text = getString(
            R.string.selected_time,
            selectedMinutes / 60,
            selectedMinutes % 60,
        )
        updateTimeCard()
    }

    // 오른쪽 아래 시각 카드: "현재 시각"/"선택 시각", 시:분, 오늘이 아니면 날짜도
    private fun updateTimeCard() {
        binding.timeCardLabel.setText(if (followingNow) R.string.time_now else R.string.time_selected)
        binding.timeCardTime.text = getString(R.string.clock_time, selectedMinutes / 60, selectedMinutes % 60)
        val today = dataDate == LocalDate.now(SEOUL_ZONE)
        binding.timeCardDate.visibility = if (today) View.GONE else View.VISIBLE
        binding.timeCardDate.text = dataDate.format(MONTH_DAY)
        // 과거나 다른 시각을 보면 내 위치 체감 효과는 끈다.
        updateFeltHere()
    }

    private fun updateDataDateLabel(observedAt: LocalDateTime? = null) {
        val date = dataDate.format(DateTimeFormatter.ofPattern("yyyy-MM-dd"))
        timeSheet.dateButton.text = if (dataDate == LocalDate.now(SEOUL_ZONE)) {
            getString(R.string.date_today, date)
        } else {
            date
        }
        timeSheet.dataDateText.text = if (observedAt == null) {
            getString(R.string.data_date, date)
        } else {
            getString(R.string.data_date_observed, date, observedAt.format(HOUR_MINUTE))
        }
        updateTimeCard()
    }

    // ---- 건물 검색 ----

    private fun configureSearch() {
        buildingAdapter = BuildingAdapter(layoutInflater)
        binding.searchResults.adapter = buildingAdapter
        binding.searchResults.setOnItemClickListener { _, _, position, _ ->
            selectBuilding(buildingAdapter.getItem(position))
        }
        BuildingSearch.ZONES.forEach { zone ->
            val chip = layoutInflater.inflate(R.layout.item_zone_chip, binding.zoneChips, false) as Chip
            chip.id = View.generateViewId()
            chip.text = zone
            chip.tag = zone
            binding.zoneChips.addView(chip)
            if (zone == selectedZone) binding.zoneChips.check(chip.id)
        }
        binding.zoneChips.setOnCheckedStateChangeListener { group, checkedIds ->
            val chip = checkedIds.firstOrNull()?.let { group.findViewById<Chip>(it) } ?: return@setOnCheckedStateChangeListener
            selectedZone = chip.tag as String
            refreshSearchResults()
        }
        binding.searchInput.setOnFocusChangeListener { _, hasFocus -> if (hasFocus) showSearchResults() }
        binding.searchInput.setOnClickListener { showSearchResults() }
        binding.searchInput.doAfterTextChanged { text ->
            binding.clearSearchButton.visibility = if (text.isNullOrEmpty()) View.GONE else View.VISIBLE
            if (suppressSearchWatcher) return@doAfterTextChanged
            showSearchResults()
        }
        binding.searchInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId != EditorInfo.IME_ACTION_SEARCH) return@setOnEditorActionListener false
            buildingAdapter.items.firstOrNull()?.let(::selectBuilding)
            true
        }
        binding.clearSearchButton.setOnClickListener {
            setSearchText("")
            hideSelection()
            if (binding.searchInput.hasFocus()) showSearchResults()
        }
    }

    private fun showSearchResults() {
        refreshSearchResults()
        binding.searchResultsCard.visibility = View.VISIBLE
        updateBackCallback()
    }

    private fun hideSearchResults() {
        binding.searchResultsCard.visibility = View.GONE
        binding.searchInput.clearFocus()
        getSystemService(InputMethodManager::class.java)
            ?.hideSoftInputFromWindow(binding.searchInput.windowToken, 0)
        updateBackCallback()
    }

    private fun refreshSearchResults() {
        val results = BuildingSearch.search(buildings, binding.searchInput.text.toString(), selectedZone)
        buildingAdapter.items = results
        binding.searchEmpty.setText(if (buildings.isEmpty()) R.string.search_loading else R.string.search_empty)
        binding.searchEmpty.visibility = if (results.isEmpty()) View.VISIBLE else View.GONE
        binding.searchResults.visibility = if (results.isEmpty()) View.GONE else View.VISIBLE
        // 목록은 최대 몇 줄까지만 펼치고 나머지는 스크롤한다.
        val rowHeight = (52 * resources.displayMetrics.density).toInt()
        binding.searchResults.layoutParams = binding.searchResults.layoutParams.apply {
            height = rowHeight * results.size.coerceAtMost(MAX_RESULT_ROWS)
        }
    }

    private fun setSearchText(text: String) {
        suppressSearchWatcher = true
        binding.searchInput.setText(text)
        suppressSearchWatcher = false
    }

    /**
     * Shows [building] in the selection card with [출발][도착]; used for a search
     * result and for a building tapped on the map. A tapped building is already on
     * screen, so [moveCamera] is false for it.
     */
    private fun selectBuilding(building: Building, moveCamera: Boolean = true) {
        selectedBuilding = building
        hideSearchResults()
        setSearchText(building.label)
        if (moveCamera) map?.animateCamera(CameraUpdateFactory.newLatLngZoom(building.latLng(), SELECTED_ZOOM), 700)
        binding.selectionNumber.text = building.number.orEmpty()
        binding.selectionNumber.visibility = if (building.number == null) View.GONE else View.VISIBLE
        binding.selectionTitle.text = building.name
        val details = BuildingSearch.details(building)
        binding.selectionDetail.text = details.joinToString("\n")
        binding.selectionDetail.visibility = if (details.isEmpty()) View.GONE else View.VISIBLE
        binding.selectionCard.visibility = View.VISIBLE
        updateBackCallback()
    }

    private fun hideSelection() {
        selectedBuilding = null
        binding.selectionCard.visibility = View.GONE
        updateBackCallback()
    }

    private fun updateBackCallback() {
        closeOverlaysOnBack.isEnabled = binding.searchResultsCard.visibility == View.VISIBLE ||
            binding.selectionCard.visibility == View.VISIBLE
    }

    private fun Building.latLng() = LatLng(latitude, longitude)

    // ---- 지도 누르기: 센서 → 건물 ----

    private fun onMapTapped(point: LatLng): Boolean {
        // 검색 결과가 열려 있으면 첫 탭은 닫기만 한다.
        if (binding.searchResultsCard.visibility == View.VISIBLE) {
            hideSearchResults()
            return true
        }
        val map = map ?: return false
        val screen = map.projection.toScreenLocation(point)
        sensorAt(screen)?.let { showSensorSheet(it); return true }
        buildingAt(screen)?.let { selectBuilding(it, moveCamera = false); return true }
        return false
    }

    // 센서 점은 작아서 손가락 크기만큼 넓게 찾는다.
    private fun sensorAt(screen: PointF): SensorSite? {
        if (!showSensors) return null
        val map = map ?: return null
        val slop = SENSOR_TAP_DP * resources.displayMetrics.density
        val box = RectF(screen.x - slop, screen.y - slop, screen.x + slop, screen.y + slop)
        return map.queryRenderedFeatures(box, MapStyle.SENSOR_LAYER).asSequence()
            .mapNotNull { SensorInfo.find(sensors, it.id(), it.getStringProperty("sensor")) }
            .firstOrNull()
    }

    private fun buildingAt(screen: PointF): Building? {
        val map = map ?: return null
        return map.queryRenderedFeatures(screen, MapStyle.BUILDING_LAYER).asSequence()
            .mapNotNull { feature ->
                val id = (if (feature.hasProperty("id")) feature.getNumberProperty("id") else null)?.toLong()
                    ?: feature.id()?.toDoubleOrNull()?.toLong()
                val name = if (feature.hasProperty("name")) feature.getStringProperty("name") else null
                BuildingSearch.findTapped(buildings, id, name)
            }
            .firstOrNull()
    }

    private fun showSensorSheet(site: SensorSite) {
        sensorSheet.sensorTitle.text = site.name
        // 측정값 API가 생기면 여기서 SensorReading을 넘기면 된다.
        fillInfoRows(sensorSheet.sensorReadingRows, SensorInfo.readingRows(null))
        sensorSheet.sensorReadingNote.visibility = View.VISIBLE
        fillInfoRows(sensorSheet.sensorSiteRows, SensorInfo.siteRows(site))
        sensorSheetDialog.show()
    }

    private fun fillInfoRows(container: ViewGroup, rows: List<Pair<String, String>>) {
        container.removeAllViews()
        rows.forEach { (label, value) ->
            val row = ItemInfoRowBinding.inflate(layoutInflater, container, true)
            row.infoLabel.text = label
            row.infoValue.text = value
        }
    }

    // ---- 출발·도착 핀 끌기 ----

    /**
     * A touch that starts on a route pin drags the pin instead of the map; any
     * other touch goes to the map as before. MapLibre has no draggable marker, so
     * this sits in front of the map's own gestures.
     */
    @SuppressLint("ClickableViewAccessibility")
    private fun configurePinDragging() {
        val touchSlop = ViewConfiguration.get(this).scaledTouchSlop
        binding.mapView.setOnTouchListener { _, event -> onMapTouch(event, touchSlop) }
    }

    private fun onMapTouch(event: MotionEvent, touchSlop: Int): Boolean {
        val map = map ?: return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val (role, pin) = pinNear(event.x, event.y) ?: return false
                dragRole = role
                dragOffset = PointF(pin.x - event.x, pin.y - event.y)
                dragDown = PointF(event.x, event.y)
                dragMoved = false
                dragOriginal = if (role == "start") routeStart else routeEnd
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val role = dragRole ?: return false
                if (!dragMoved && hypot(event.x - dragDown.x, event.y - dragDown.y) < touchSlop) return true
                dragMoved = true
                val point = map.projection.fromScreenLocation(PointF(event.x + dragOffset.x, event.y + dragOffset.y))
                val place = (dragOriginal ?: return true).copy(point = point)
                if (role == "start") routeStart = place else routeEnd = place
                showRouteEnds()
                return true
            }
            MotionEvent.ACTION_UP -> {
                val role = dragRole ?: return false
                dragRole = null
                if (dragMoved) finishPinDrag(role, PointF(event.x + dragOffset.x, event.y + dragOffset.y))
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                val role = dragRole ?: return false
                dragRole = null
                if (role == "start") routeStart = dragOriginal else routeEnd = dragOriginal
                showRouteEnds()
                return true
            }
            // 끄는 동안 두 번째 손가락(확대·회전)도 지도에 넘기지 않는다.
            else -> return dragRole != null
        }
    }

    /** The route pin within reach of a touch at [x], [y] and its screen point, nearest first. */
    private fun pinNear(x: Float, y: Float): Pair<String, PointF>? {
        val map = map ?: return null
        val reach = PIN_TOUCH_DP * resources.displayMetrics.density
        return listOfNotNull(routeStart?.let { "start" to it }, routeEnd?.let { "end" to it })
            .map { (role, place) -> role to map.projection.toScreenLocation(place.point) }
            .map { (role, pin) -> Triple(role, pin, hypot(pin.x - x, pin.y - y)) }
            .filter { it.third <= reach }
            .minByOrNull { it.third }
            ?.let { it.first to it.second }
    }

    // 놓은 자리가 건물이면 그 이름을, 아니면 "지도에서 고른 곳"으로 부르고 경로를 다시 구한다.
    private fun finishPinDrag(role: String, screen: PointF) {
        val map = map ?: return
        val point = map.projection.fromScreenLocation(screen)
        val name = buildingAt(screen)?.label ?: getString(R.string.route_map_point)
        val place = Place(name, point)
        if (role == "start") routeStart = place else routeEnd = place
        hideSearchResults()
        onRouteEndsChanged()
    }

    // ---- 길찾기 ----

    private fun useSelectedBuildingAsRouteEnd(start: Boolean) {
        val building = selectedBuilding ?: return
        val place = Place(building.label, building.latLng())
        if (start) routeStart = place else routeEnd = place
        hideSelection()
        onRouteEndsChanged()
    }

    private fun pickRoutePoint(point: LatLng) {
        val place = Place(getString(R.string.route_map_point), point)
        when {
            // 이미 경로가 있으면 새 출발지부터 다시 고른다.
            routeStart != null && routeEnd != null -> { routeStart = place; routeEnd = null }
            routeStart == null -> routeStart = place
            else -> routeEnd = place
        }
        onRouteEndsChanged()
    }

    // 출발·도착이 다 정해지면 경로를 구하고, 하나만 있으면 나머지를 고르라고 안내한다.
    private fun onRouteEndsChanged() {
        showRouteEnds()
        val start = routeStart
        val end = routeEnd
        if (start != null && end != null) {
            requestRoute()
            return
        }
        routeCall?.cancel()
        showRoute(null)
        binding.routePanel.visibility = if (start == null && end == null) View.GONE else View.VISIBLE
        binding.routeText.text = when {
            start != null -> getString(R.string.route_pick_end, start.name)
            end != null -> getString(R.string.route_pick_start, end.name)
            else -> ""
        }
    }

    // ---- 내 위치 ----

    private fun onMyLocationClicked() {
        val granted = listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            .any { ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED }
        if (granted) {
            showMyLocation()
        } else {
            locationPermissionRequest.launch(
                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            )
        }
    }

    private fun hasLocationPermission(): Boolean =
        listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            .any { ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED }

    /** Shows the location puck and starts location updates; false without a map or permission. */
    @SuppressLint("MissingPermission")
    private fun activateLocation(): Boolean {
        val map = map ?: return false
        val style = mapStyle ?: return false
        if (!hasLocationPermission()) return false
        val component = map.locationComponent
        if (!component.isLocationComponentActivated) {
            component.activateLocationComponent(
                LocationComponentActivationOptions.builder(this, style)
                    .useDefaultLocationEngine(true)
                    .build()
            )
        }
        component.isLocationComponentEnabled = true
        component.renderMode = RenderMode.COMPASS
        startLocationUpdates()
        component.lastKnownLocation?.let { myLocation = it }
        if (!showHeatmap && feltGrid == null) requestFeltGrid()
        updateFeltHere()
        return true
    }

    @SuppressLint("MissingPermission")
    private fun startLocationUpdates() {
        if (locationUpdatesOn || !hasLocationPermission()) return
        val engine = map?.locationComponent?.takeIf { it.isLocationComponentActivated }?.locationEngine ?: return
        engine.requestLocationUpdates(
            LocationEngineRequest.Builder(LOCATION_INTERVAL_MS)
                .setPriority(LocationEngineRequest.PRIORITY_HIGH_ACCURACY)
                .setFastestInterval(LOCATION_INTERVAL_MS / 2)
                .build(),
            locationCallback,
            Looper.getMainLooper(),
        )
        locationUpdatesOn = true
    }

    private fun stopLocationUpdates() {
        if (!locationUpdatesOn) return
        map?.locationComponent?.locationEngine?.removeLocationUpdates(locationCallback)
        locationUpdatesOn = false
    }

    // Called only once a location permission is granted.
    private fun showMyLocation() {
        val map = map
        if (map == null || !activateLocation()) {
            Toast.makeText(this, R.string.location_searching, Toast.LENGTH_SHORT).show()
            return
        }
        val component = map.locationComponent
        val last = component.lastKnownLocation
        if (last == null) {
            // 위치가 잡히면 카메라가 따라가게 하고, 사용자가 지도를 움직이면 풀린다.
            component.cameraMode = CameraMode.TRACKING
            Toast.makeText(this, R.string.location_searching, Toast.LENGTH_SHORT).show()
        } else {
            map.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(last.latitude, last.longitude), SELECTED_ZOOM), 700)
        }
    }

    // ---- 내 위치 체감온도 ----

    /** True when the selected date and time are now (the slider stops at 06:00–20:00). */
    private fun isNow(): Boolean {
        val now = LocalDateTime.now(SEOUL_ZONE)
        return followingNow && dataDate == now.toLocalDate() &&
            abs(selectedMinutes - (now.hour * 60 + now.minute)) <= NOW_TOLERANCE_MINUTES
    }

    /**
     * Edge effect and "내 위치 체감" line from the UTCI cells within about 10 m of
     * where you are, only while looking at now and standing on the campus grid.
     */
    private fun updateFeltHere() {
        if (!::binding.isInitialized) return
        val grid = feltGrid
        val location = myLocation
        val utci = if (grid != null && location != null && isNow() && hasLocationPermission()) {
            grid.medianAround(location.latitude, location.longitude, FELT_RADIUS_M)
        } else {
            null
        }
        if (utci == null) {
            binding.feltEdge.setStage(FeltStage.COMFORT)
            binding.feltCard.visibility = View.GONE
            return
        }
        binding.feltEdge.setStage(FeltStage.of(utci))
        binding.feltText.text = getString(R.string.felt_here, utci.roundToInt(), FeltStage.label(utci))
        binding.feltCard.visibility = View.VISIBLE
    }

    // In shadow mode the heatmap is not fetched, so get the grid alone for the effect.
    private fun requestFeltGrid() {
        if (mapStyle == null || !isNow() || !hasLocationPermission()) return
        val url = apiUrl("api/microclimate").addQueryParameter("datetime", selectedDateTime()).build()
        feltCall = fetchJson(
            url,
            feltCall,
            onError = { feltGrid = null; updateFeltHere() },
            reportErrors = false,
            parse = UtciHeatmap::fromResponse,
        ) { _, heatmap ->
            feltGrid = heatmap.grid
            updateFeltHere()
        }
    }

    // ---- 바람 ----

    private fun requestWind() {
        if (mapStyle == null || !showWind) return
        binding.windText.visibility = View.VISIBLE
        binding.windText.text = getString(R.string.wind_loading)
        val url = apiUrl("api/wind").addQueryParameter("datetime", selectedDateTime()).build()
        windCall = fetchJson(
            url,
            windCall,
            onError = { code ->
                mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.WIND_SOURCE)?.setGeoJson(EMPTY_FEATURE_COLLECTION)
                binding.windText.text = if (code == null) getString(R.string.network_error, "")
                else if (code == 404) getString(R.string.wind_unavailable) else getString(R.string.http_error, code)
            },
            reportErrors = false,
        ) { root ->
            if (!showWind) return@fetchJson
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.WIND_SOURCE)?.setGeoJson(root.toString())
            val wind = root.getJSONObject("wind")
            val speed = wind.optDouble("asos_speed_ms", 0.0)
            val direction = wind.optDouble("direction_deg", Double.NaN)
            binding.windText.text = when {
                direction.isNaN() -> getString(R.string.wind_calm)
                wind.optBoolean("wind_field") -> getString(R.string.wind_field, WindDirection.name(direction), speed)
                else -> getString(R.string.wind_uniform, WindDirection.name(direction), speed)
            }
        }
    }

    // ---- 현재 날씨 ----

    private fun requestWeather() {
        weatherCall = fetchJson(
            apiUrl("api/weather").build(),
            weatherCall,
            onError = { if (weatherDetail == null) binding.weatherCard.visibility = View.GONE },
            reportErrors = false,
        ) { root -> showWeather(root) }
    }

    private fun showWeather(root: JSONObject) {
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
        binding.weatherTemp.text = if (temp.isNaN()) getString(R.string.weather_temp_unknown)
        else getString(R.string.weather_temp, temp.roundToInt())
        binding.weatherSky.text = when (sky) {
            Sky.CLEAR -> getString(R.string.weather_clear)
            Sky.PARTLY_CLOUDY -> getString(R.string.weather_partly_cloudy)
            Sky.OVERCAST -> getString(R.string.weather_overcast)
            null -> ""
        }
        val observedAt = weather.optString("observed_at").takeIf { it.isNotEmpty() }?.let {
            runCatching { OffsetDateTime.parse(it).atZoneSameInstant(SEOUL_ZONE).toLocalDateTime() }.getOrNull()
        }
        // latest: 지금은 아직 관측 전이라 가장 최근 관측값을 보여 준다.
        val showObserved = root.optBoolean("latest") && observedAt != null
        binding.weatherObserved.visibility = if (showObserved) View.VISIBLE else View.GONE
        if (showObserved) binding.weatherObserved.text = getString(R.string.weather_observed, observedAt!!.format(MONTH_DAY_TIME))

        val humidity = weather.optDouble("relative_humidity", Double.NaN)
        val wind = weather.optDouble("wind_ms", Double.NaN)
        weatherDetail = listOfNotNull(
            observedAt?.let { getString(R.string.weather_detail_station, weather.optString("station"), it.format(MONTH_DAY_TIME)) },
            temp.takeUnless { it.isNaN() }?.let { getString(R.string.weather_detail_temp, it) },
            humidity.takeUnless { it.isNaN() }?.let { getString(R.string.weather_detail_humidity, it) },
            wind.takeUnless { it.isNaN() }?.let { getString(R.string.weather_detail_wind, it) },
            cloud.takeUnless { it.isNaN() }?.let { getString(R.string.weather_detail_cloud, (it * 10).roundToInt()) },
        ).joinToString("\n")
        binding.weatherCard.visibility = View.VISIBLE
    }

    private fun showWeatherDetail() {
        val detail = weatherDetail ?: return
        AlertDialog.Builder(this)
            .setTitle(R.string.weather_detail_title)
            .setMessage(detail)
            .setPositiveButton(R.string.weather_close, null)
            .show()
    }

    // ---- 지도 데이터 ----

    private fun installDataLayers(style: Style) {
        // 위성사진, 그림자, 건물 순으로 쌓고 모두 기본 지도의 라벨 아래에 둔다.
        // 체감온도 히트맵은 첫 응답에서 그림자 아래(위성사진 위)에 추가한다.
        val satelliteTiles = TileSet("2.2.0", BuildConfig.API_BASE_URL + "api/tiles/satellite/{z}/{x}/{y}.jpeg").apply {
            minZoom = MapStyle.SATELLITE_MIN_ZOOM
            maxZoom = MapStyle.SATELLITE_MAX_ZOOM
        }
        style.addSource(RasterSource(MapStyle.SATELLITE_SOURCE, satelliteTiles, 256))
        addBelowLabels(style, RasterLayer(MapStyle.SATELLITE_LAYER, MapStyle.SATELLITE_SOURCE))
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
        // 바람 화살표는 건물 바로 위, 라벨 아래에 둔다. 불어가는 쪽(direction + 180°)을 가리킨다.
        ContextCompat.getDrawable(this, R.drawable.ic_wind_arrow)?.let {
            style.addImage(MapStyle.WIND_ARROW_IMAGE, it.toBitmap())
        }
        style.addSource(GeoJsonSource(MapStyle.WIND_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayerAbove(
            SymbolLayer(MapStyle.WIND_LAYER, MapStyle.WIND_SOURCE).withProperties(
                iconImage(MapStyle.WIND_ARROW_IMAGE),
                iconRotate(sum(get("direction_deg"), literal(180))),
                iconRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP),
                iconPitchAlignment(Property.ICON_PITCH_ALIGNMENT_MAP),
                iconAllowOverlap(true),
                iconIgnorePlacement(true),
                // 약한 바람은 작고 흐리게, 센 바람은 크고 진하게
                iconSize(interpolate(linear(), get("speed_ms"), stop(0, 0.45f), stop(2, 0.7f), stop(5, 1.0f), stop(8, 1.3f))),
                iconOpacity(interpolate(linear(), get("speed_ms"), stop(0, 0.35f), stop(2, 0.65f), stop(5, 0.9f), stop(8, 1f))),
            ),
            MapStyle.BUILDING_LAYER,
        )
        // 경로는 라벨 위에 그려 눈에 띄게 하고, 센서는 그보다 위에 둔다.
        style.addSource(GeoJsonSource(MapStyle.ROUTE_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            LineLayer(MapStyle.ROUTE_CASING_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(Color.WHITE),
                lineWidth(9f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addLayer(
            LineLayer(MapStyle.ROUTE_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(
                    // 추울 때(mode=cold)의 coolest는 햇볕길이라 따뜻한 색으로 그린다.
                    switchCase(
                        all(eq(get("mode"), literal("cold")), eq(get("kind"), literal("coolest"))),
                        color(MapStyle.routeSunnyColor),
                        match(
                            get("kind"), color(MapStyle.routeShortestColor),
                            stop("balanced", color(MapStyle.routeBalancedColor)),
                            stop("coolest", color(MapStyle.routeCoolestColor)),
                        ),
                    )
                ),
                lineWidth(5f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addSource(GeoJsonSource(MapStyle.ROUTE_POINT_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.ROUTE_POINT_LAYER, MapStyle.ROUTE_POINT_SOURCE).withProperties(
                circleRadius(8f),
                circleColor(
                    match(get("role"), color(MapStyle.routeEndColor), stop("start", color(MapStyle.routeStartColor)))
                ),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(3f),
            )
        )
        // 센서 위치는 다른 모든 층과 라벨 위에 둬서 히트맵·건물에 가리지 않게 한다.
        style.addSource(GeoJsonSource(MapStyle.SENSOR_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.SENSOR_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                circleRadius(MapStyle.SENSOR_RADIUS),
                circleColor(MapStyle.sensorColor),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(MapStyle.SENSOR_STROKE_WIDTH),
                circlePitchAlignment(Property.CIRCLE_PITCH_ALIGNMENT_MAP),
            )
        )
        style.addLayer(
            SymbolLayer(MapStyle.SENSOR_LABEL_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                textField(get("sensor")),
                textFont(MapStyle.labelFont),
                textSize(12f),
                textColor(MapStyle.sensorColor),
                textHaloColor(Color.WHITE),
                textHaloWidth(1.5f),
                textAnchor(Property.TEXT_ANCHOR_TOP),
                textOffset(arrayOf(0f, 0.9f)),
            )
        )
        updateLayerMode()
        updateBaseMap()
        updateSensors()
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
            updateBaseMap()
        } else {
            source.setCoordinates(heatmap.quad)
            source.setImage(heatmap.bitmap)
            updateLayerMode()
        }
    }

    private fun requestBuildings() {
        fetchJson(apiUrl("api/buildings").build(), null) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.BUILDING_SOURCE)
                ?.setGeoJson(root.toString())
            buildings = Places.buildings(root)
            if (binding.searchResultsCard.visibility == View.VISIBLE) refreshSearchResults()
        }
    }

    private fun requestSensors() {
        fetchJson(apiUrl("api/sensors").build(), null) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.SENSOR_SOURCE)
                ?.setGeoJson(root.toString())
            sensors = Places.sensors(root)
        }
    }

    private fun requestDataDateThenRefresh() {
        fetchJson(
            apiUrl("api/weather/period").build(),
            null,
            onError = { requestForSelectedTime() },
        ) { root ->
            val latest = OffsetDateTime.parse(root.getString("latest_observation"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDateTime()
            latestObservation = latest
            firstDate = OffsetDateTime.parse(root.getString("start"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDate()
            val today = LocalDate.now(SEOUL_ZONE)
            defaultDate = if (root.getBoolean("realtime") && latest.toLocalDate() == today) {
                today
            } else {
                LocalDate.parse(root.getString("latest_full_date"))
            }
            dataDate = defaultDate
            updateDataDateLabel()
            requestForSelectedTime()
        }
    }

    private fun requestForSelectedTime() {
        if (mapStyle == null) return
        if (showHeatmap) requestMicroclimate() else { requestShadows(); requestFeltGrid() }
        if (showWind) requestWind()
        // 그늘은 시각마다 달라지므로 경로도 같은 시각으로 다시 구한다.
        requestRoute()
    }

    private fun requestRoute() {
        val start = routeStart ?: return
        val end = routeEnd ?: return
        if (mapStyle == null) return
        binding.routePanel.visibility = View.VISIBLE
        binding.routeText.text = getString(R.string.route_loading)
        val url = apiUrl("api/route")
            .addQueryParameter("from_lat", start.point.latitude.toString())
            .addQueryParameter("from_lon", start.point.longitude.toString())
            .addQueryParameter("to_lat", end.point.latitude.toString())
            .addQueryParameter("to_lon", end.point.longitude.toString())
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        routeCall = fetchJson(
            url,
            routeCall,
            onError = { binding.routeText.text = getString(R.string.route_failed); showRoute(null) },
        ) { root ->
            showRoute(root.getJSONObject("routes").toString())
            binding.routeText.text = "${start.name} → ${end.name}\n" + RouteSummary.text(root)
        }
    }

    private fun showRoute(geoJson: String?) {
        mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_SOURCE)?.setGeoJson(geoJson ?: EMPTY_FEATURE_COLLECTION)
    }

    private fun showRouteEnds() {
        mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_POINT_SOURCE)
            ?.setGeoJson(Places.endpointsGeoJson(routeStart, routeEnd))
    }

    private fun clearRoute() {
        routeCall?.cancel()
        routeStart = null
        routeEnd = null
        showRoute(null)
        showRouteEnds()
        binding.routePanel.visibility = View.GONE
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
        val forNow = isNow()
        val url = apiUrl("api/microclimate")
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        microclimateCall = fetchJson(
            url,
            microclimateCall,
            onError = { code ->
                if (code == 404) showNotObservedYet()
                feltGrid = null
                updateFeltHere()
            },
            parse = UtciHeatmap::fromResponse,
        ) { root, heatmap ->
            showHeatmap(heatmap)
            feltGrid = if (forNow) heatmap.grid else null
            updateFeltHere()
            val observedAt = OffsetDateTime.parse(root.getJSONObject("weather").getString("observed_at"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDateTime()
            updateDataDateLabel(observedAt)
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

    // The server answers 404 for an instant more than a few hours past its latest
    // observation, i.e. later today than has been observed.
    private fun showNotObservedYet() {
        mapStyle?.getLayer(MapStyle.HEATMAP_LAYER)?.setProperties(visibility(Property.NONE))
        binding.statusText.text = latestObservation?.let {
            getString(R.string.not_observed_yet, it.format(HOUR_MINUTE))
        } ?: getString(R.string.not_observed_yet_unknown)
    }

    private fun apiUrl(path: String): HttpUrl.Builder =
        (BuildConfig.API_BASE_URL + path).toHttpUrl().newBuilder()

    private fun fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        reportErrors: Boolean = true,
        onSuccess: (JSONObject) -> Unit,
    ): Call = fetchJson(url, previous, onError, reportErrors, parse = { }) { root, _ -> onSuccess(root) }

    /**
     * GET [url] and hand the parsed body to [onSuccess] on the UI thread. [parse]
     * runs on the network thread first, for work such as building a bitmap.
     * [onError] gets the HTTP status, or null when the request never got one.
     * Errors are also shown in the status line unless [reportErrors] is false.
     */
    private fun <T> fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        reportErrors: Boolean = true,
        parse: (JSONObject) -> T,
        onSuccess: (JSONObject, T) -> Unit,
    ): Call {
        previous?.cancel()
        val call = client.newCall(Request.Builder().url(url).build())
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (call.isCanceled()) return
                runOnUiThread {
                    if (reportErrors) binding.statusText.text = getString(R.string.network_error, error.localizedMessage)
                    onError?.invoke(null)
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        runOnUiThread {
                            if (reportErrors) binding.statusText.text = getString(R.string.http_error, it.code)
                            onError?.invoke(it.code)
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

    override fun onStart() {
        super.onStart()
        binding.mapView.onStart()
        if (map?.locationComponent?.isLocationComponentActivated == true) startLocationUpdates()
    }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { stopLocationUpdates(); binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        shadowCall?.cancel()
        microclimateCall?.cancel()
        routeCall?.cancel()
        weatherCall?.cancel()
        windCall?.cancel()
        feltCall?.cancel()
        timeSheetDialog.dismiss()
        mapSettingsDialog.dismiss()
        sensorSheetDialog.dismiss()
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
        private val HOUR_MINUTE = DateTimeFormatter.ofPattern("HH:mm")
        private val MONTH_DAY = DateTimeFormatter.ofPattern("MM/dd")
        private val MONTH_DAY_TIME = DateTimeFormatter.ofPattern("MM/dd HH:mm")
        private const val SELECTED_ZOOM = 17.5
        private const val MAX_RESULT_ROWS = 6
        // 출발·도착 핀(반지름 8 + 테두리 3)보다 넉넉히: 이 안에서 누르면 핀을 끈다.
        private const val PIN_TOUCH_DP = 28f
        private const val SENSOR_TAP_DP = 14f
        private const val LOCATION_INTERVAL_MS = 5_000L
        private const val FELT_RADIUS_M = 10.0
        private const val NOW_TOLERANCE_MINUTES = 30
        private const val START_MINUTES = 6 * 60
        private const val END_MINUTES = 20 * 60
        private const val EMPTY_FEATURE_COLLECTION =
            "{\"type\":\"FeatureCollection\",\"features\":[]}"
    }
}

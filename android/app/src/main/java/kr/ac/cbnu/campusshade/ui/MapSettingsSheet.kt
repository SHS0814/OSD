package kr.ac.cbnu.campusshade.ui

import android.content.res.ColorStateList
import android.graphics.Typeface
import android.view.View
import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import com.google.android.material.bottomsheet.BottomSheetDialog
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.databinding.ItemMapIconToggleBinding
import kr.ac.cbnu.campusshade.databinding.ItemMapPictureOptionBinding
import kr.ac.cbnu.campusshade.databinding.SheetMapSettingsBinding

/**
 * The map settings bottom sheet: 3D/2D, satellite/plain base map and
 * heatmap/shadows as pairs of picture cards, wind arrows and sensor sites as
 * round on/off icon buttons. Each choice is reported as the value the user
 * picked; showing a value changes the cards and buttons only.
 */
class MapSettingsSheet(private val activity: AppCompatActivity) {
    private val sheet = SheetMapSettingsBinding.inflate(activity.layoutInflater)
    private val dialog = BottomSheetDialog(activity, R.style.ThemeOverlay_CampusShade_RoundedSheet)
        .apply { setContentView(sheet.root) }

    var on3dPicked: (Boolean) -> Unit = {}
    var onSatellitePicked: (Boolean) -> Unit = {}
    var onHeatmapPicked: (Boolean) -> Unit = {}
    var onWindPicked: (Boolean) -> Unit = {}
    var onSensorsPicked: (Boolean) -> Unit = {}

    private val brand = ContextCompat.getColor(activity, R.color.brand)
    private val textPrimary = ContextCompat.getColor(activity, R.color.text_primary)
    private val iconIdle = ContextCompat.getColor(activity, R.color.text_secondary)
    private val divider = ContextCompat.getColor(activity, R.color.divider)
    private val density = activity.resources.displayMetrics.density

    private var wind = false
    private var sensors = false

    init {
        setUpPair(
            sheet.viewMode3d, sheet.viewMode2d, R.string.map_settings_view,
            R.drawable.thumb_view_3d, R.string.view_3d,
            R.drawable.thumb_view_2d, R.string.view_2d,
        ) { on3dPicked(it) }
        setUpPair(
            sheet.baseMapSatellite, sheet.baseMapNormal, R.string.map_settings_base,
            R.drawable.thumb_base_satellite, R.string.show_satellite,
            R.drawable.thumb_base_plain, R.string.show_basemap,
        ) { onSatellitePicked(it) }
        setUpPair(
            sheet.layerHeatmap, sheet.layerShadow, R.string.map_settings_layer,
            R.drawable.thumb_layer_utci, R.string.show_heatmap,
            R.drawable.thumb_layer_shadow, R.string.show_shadows,
        ) { onHeatmapPicked(it) }

        setUpToggle(sheet.windToggle, R.drawable.ic_air, R.string.wind_on) {
            wind = !wind
            showToggle(sheet.windToggle, wind)
            onWindPicked(wind)
        }
        setUpToggle(sheet.sensorsToggle, R.drawable.ic_sensors, R.string.sensors_on) {
            sensors = !sensors
            showToggle(sheet.sensorsToggle, sensors)
            onSensorsPicked(sensors)
        }
        showToggle(sheet.windToggle, false)
        showToggle(sheet.sensorsToggle, false)
    }

    fun show() = dialog.show()

    fun dismiss() = dialog.dismiss()

    fun show3d(is3d: Boolean) = showPair(sheet.viewMode3d, sheet.viewMode2d, is3d)

    fun showSatellite(satellite: Boolean) = showPair(sheet.baseMapSatellite, sheet.baseMapNormal, satellite)

    fun showHeatmap(heatmap: Boolean) = showPair(sheet.layerHeatmap, sheet.layerShadow, heatmap)

    fun showWind(wind: Boolean) {
        this.wind = wind
        showToggle(sheet.windToggle, wind)
    }

    fun showSensors(sensors: Boolean) {
        this.sensors = sensors
        showToggle(sheet.sensorsToggle, sensors)
    }

    /**
     * Two picture cards where exactly one is picked. Tapping the card that is
     * not picked reports `true` for [first] and `false` for [second]; tapping
     * the picked one does nothing, like a toggle group that needs a choice.
     */
    private fun setUpPair(
        first: ItemMapPictureOptionBinding,
        second: ItemMapPictureOptionBinding,
        @StringRes group: Int,
        @DrawableRes firstPicture: Int,
        @StringRes firstLabel: Int,
        @DrawableRes secondPicture: Int,
        @StringRes secondLabel: Int,
        onPicked: (Boolean) -> Unit,
    ) {
        for ((option, picture, label) in listOf(
            Triple(first, firstPicture, firstLabel),
            Triple(second, secondPicture, secondLabel),
        )) {
            option.picture.setImageResource(picture)
            option.label.setText(label)
            option.root.contentDescription =
                activity.getString(R.string.map_settings_choice, activity.getString(group), activity.getString(label))
        }
        first.root.setOnClickListener {
            if (!first.root.isSelected) {
                showPair(first, second, true)
                onPicked(true)
            }
        }
        second.root.setOnClickListener {
            if (!second.root.isSelected) {
                showPair(first, second, false)
                onPicked(false)
            }
        }
        showPair(first, second, true)
    }

    private fun showPair(first: ItemMapPictureOptionBinding, second: ItemMapPictureOptionBinding, firstPicked: Boolean) {
        showOption(first, firstPicked)
        showOption(second, !firstPicked)
    }

    /** Picked: brand outline, check mark and bold brand label; otherwise thin grey outline. */
    private fun showOption(option: ItemMapPictureOptionBinding, picked: Boolean) {
        option.root.isSelected = picked
        option.frame.strokeColor = if (picked) brand else divider
        option.frame.strokeWidth = ((if (picked) 2 else 1) * density).toInt()
        option.check.visibility = if (picked) View.VISIBLE else View.GONE
        option.label.setTextColor(if (picked) brand else textPrimary)
        option.label.setTypeface(null, if (picked) Typeface.BOLD else Typeface.NORMAL)
        ViewCompat.setStateDescription(
            option.root,
            activity.getString(if (picked) R.string.state_selected else R.string.state_not_selected),
        )
    }

    private fun setUpToggle(
        toggle: ItemMapIconToggleBinding,
        @DrawableRes icon: Int,
        @StringRes label: Int,
        onClick: () -> Unit,
    ) {
        toggle.icon.setImageResource(icon)
        toggle.label.setText(label)
        toggle.root.contentDescription = activity.getString(label)
        toggle.root.setOnClickListener { onClick() }
    }

    /** On: tinted circle with a brand outline, brand icon, check mark and bold label. */
    private fun showToggle(toggle: ItemMapIconToggleBinding, on: Boolean) {
        toggle.root.isSelected = on
        toggle.icon.imageTintList = ColorStateList.valueOf(if (on) brand else iconIdle)
        toggle.check.visibility = if (on) View.VISIBLE else View.GONE
        toggle.label.setTextColor(if (on) brand else textPrimary)
        toggle.label.setTypeface(null, if (on) Typeface.BOLD else Typeface.NORMAL)
        ViewCompat.setStateDescription(
            toggle.root,
            activity.getString(if (on) R.string.state_on else R.string.state_off),
        )
    }
}

package kr.ac.cbnu.campusshade.ui

import android.view.View
import android.widget.SeekBar
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomsheet.BottomSheetDialog
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import kr.ac.cbnu.campusshade.databinding.SheetTimeBinding
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * The time card at the bottom right and the bottom sheet it opens: a slider
 * for the time of day, the date and "현재 시각". The sheet is made once and
 * reopened.
 */
class TimeSheet(private val activity: AppCompatActivity, private val binding: ActivityMainBinding) {
    private val sheet = SheetTimeBinding.inflate(activity.layoutInflater)
    private val dialog = BottomSheetDialog(activity).apply { setContentView(sheet.root) }

    /** Slider moved to [progress] (minutes after its start); [fromUser] false when set in code. */
    var onSlide: (progress: Int, fromUser: Boolean) -> Unit = { _, _ -> }
    var onNow: () -> Unit = {}
    var onPickDate: () -> Unit = {}

    init {
        sheet.timeSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) = onSlide(progress, fromUser)
            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
        sheet.nowButton.setOnClickListener { onNow() }
        sheet.dateButton.setOnClickListener { onPickDate() }
        binding.timeCard.setOnClickListener { dialog.show() }
    }

    fun setProgress(progress: Int) {
        sheet.timeSlider.progress = progress
    }

    fun showSelectedTime(minutes: Int) {
        sheet.selectedTime.text = activity.getString(R.string.selected_time, minutes / 60, minutes % 60)
    }

    // 오른쪽 아래 시각 카드: "현재 시각"/"선택 시각", 시:분, 오늘이 아니면 날짜도
    fun showCard(followingNow: Boolean, minutes: Int, date: LocalDate, today: LocalDate) {
        binding.timeCardLabel.setText(if (followingNow) R.string.time_now else R.string.time_selected)
        binding.timeCardTime.text = activity.getString(R.string.clock_time, minutes / 60, minutes % 60)
        binding.timeCardDate.visibility = if (date == today) View.GONE else View.VISIBLE
        binding.timeCardDate.text = date.format(MONTH_DAY)
    }

    fun showDataDate(date: LocalDate, today: LocalDate, observedAt: LocalDateTime?) {
        val text = date.format(DateTimeFormatter.ofPattern("yyyy-MM-dd"))
        sheet.dateButton.text = if (date == today) activity.getString(R.string.date_today, text) else text
        sheet.dataDateText.text = if (observedAt == null) {
            activity.getString(R.string.data_date, text)
        } else {
            activity.getString(R.string.data_date_observed, text, observedAt.format(HOUR_MINUTE))
        }
    }

    fun dismiss() = dialog.dismiss()

    private companion object {
        val HOUR_MINUTE: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")
        val MONTH_DAY: DateTimeFormatter = DateTimeFormatter.ofPattern("MM/dd")
    }
}

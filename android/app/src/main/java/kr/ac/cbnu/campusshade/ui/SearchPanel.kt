package kr.ac.cbnu.campusshade.ui

import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import com.google.android.material.chip.Chip
import kr.ac.cbnu.campusshade.Building
import kr.ac.cbnu.campusshade.BuildingAdapter
import kr.ac.cbnu.campusshade.BuildingSearch
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding

/**
 * The search box with zone chips and results at the top, and the card of the
 * selected building ([출발][도착]) at the bottom. Back closes the results, then
 * the card.
 */
class SearchPanel(private val activity: AppCompatActivity, private val binding: ActivityMainBinding) {
    /** Bring [Building] into view; called for a search result, not for a building tapped on the map. */
    var onFocus: (Building) -> Unit = {}
    /** Use the selected building as the route's start ([start] true) or end. */
    var onRouteEnd: (building: Building, start: Boolean) -> Unit = { _, _ -> }

    var buildings: List<Building> = emptyList()
        set(value) {
            field = value
            if (isShowingResults) refreshResults()
        }
    var selectedBuilding: Building? = null
        private set
    val isShowingResults: Boolean get() = binding.searchResultsCard.visibility == View.VISIBLE

    private var selectedZone = BuildingSearch.ALL
    private var suppressSearchWatcher = false
    private val adapter = BuildingAdapter(activity.layoutInflater)
    private val closeOnBack = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            if (isShowingResults) hideResults() else hideSelection()
        }
    }

    init {
        activity.onBackPressedDispatcher.addCallback(activity, closeOnBack)
        binding.searchResults.adapter = adapter
        binding.searchResults.setOnItemClickListener { _, _, position, _ ->
            select(adapter.getItem(position))
        }
        BuildingSearch.ZONES.forEach { zone ->
            val chip = activity.layoutInflater.inflate(R.layout.item_zone_chip, binding.zoneChips, false) as Chip
            chip.id = View.generateViewId()
            chip.text = zone
            chip.tag = zone
            binding.zoneChips.addView(chip)
            if (zone == selectedZone) binding.zoneChips.check(chip.id)
        }
        binding.zoneChips.setOnCheckedStateChangeListener { group, checkedIds ->
            val chip = checkedIds.firstOrNull()?.let { group.findViewById<Chip>(it) } ?: return@setOnCheckedStateChangeListener
            selectedZone = chip.tag as String
            refreshResults()
        }
        binding.searchInput.setOnFocusChangeListener { _, hasFocus -> if (hasFocus) showResults() }
        binding.searchInput.setOnClickListener { showResults() }
        binding.searchInput.doAfterTextChanged { text ->
            binding.clearSearchButton.visibility = if (text.isNullOrEmpty()) View.GONE else View.VISIBLE
            if (suppressSearchWatcher) return@doAfterTextChanged
            showResults()
        }
        binding.searchInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId != EditorInfo.IME_ACTION_SEARCH) return@setOnEditorActionListener false
            adapter.items.firstOrNull()?.let { select(it) }
            true
        }
        binding.clearSearchButton.setOnClickListener {
            setSearchText("")
            hideSelection()
            if (binding.searchInput.hasFocus()) showResults()
        }
        binding.routeFromButton.setOnClickListener { selectedBuilding?.let { onRouteEnd(it, true) } }
        binding.routeToButton.setOnClickListener { selectedBuilding?.let { onRouteEnd(it, false) } }
        binding.selectionCloseButton.setOnClickListener { hideSelection() }
    }

    fun showResults() {
        refreshResults()
        binding.searchResultsCard.visibility = View.VISIBLE
        updateBackCallback()
    }

    fun hideResults() {
        binding.searchResultsCard.visibility = View.GONE
        binding.searchInput.clearFocus()
        activity.getSystemService(InputMethodManager::class.java)
            ?.hideSoftInputFromWindow(binding.searchInput.windowToken, 0)
        updateBackCallback()
    }

    private fun refreshResults() {
        val results = BuildingSearch.search(buildings, binding.searchInput.text.toString(), selectedZone)
        adapter.items = results
        binding.searchEmpty.setText(if (buildings.isEmpty()) R.string.search_loading else R.string.search_empty)
        binding.searchEmpty.visibility = if (results.isEmpty()) View.VISIBLE else View.GONE
        binding.searchResults.visibility = if (results.isEmpty()) View.GONE else View.VISIBLE
        // 목록은 최대 몇 줄까지만 펼치고 나머지는 스크롤한다.
        val rowHeight = (52 * activity.resources.displayMetrics.density).toInt()
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
    fun select(building: Building, moveCamera: Boolean = true) {
        selectedBuilding = building
        hideResults()
        setSearchText(building.label)
        if (moveCamera) onFocus(building)
        binding.selectionNumber.text = building.number.orEmpty()
        binding.selectionNumber.visibility = if (building.number == null) View.GONE else View.VISIBLE
        binding.selectionTitle.text = building.name
        val details = BuildingSearch.details(building)
        binding.selectionDetail.text = details.joinToString("\n")
        binding.selectionDetail.visibility = if (details.isEmpty()) View.GONE else View.VISIBLE
        binding.selectionCard.visibility = View.VISIBLE
        updateBackCallback()
    }

    fun hideSelection() {
        selectedBuilding = null
        binding.selectionCard.visibility = View.GONE
        updateBackCallback()
    }

    private fun updateBackCallback() {
        closeOnBack.isEnabled = binding.searchResultsCard.visibility == View.VISIBLE ||
            binding.selectionCard.visibility == View.VISIBLE
    }

    private companion object {
        const val MAX_RESULT_ROWS = 6
    }
}

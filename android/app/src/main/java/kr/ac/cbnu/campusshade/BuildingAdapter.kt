package kr.ac.cbnu.campusshade

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import kr.ac.cbnu.campusshade.databinding.ItemBuildingBinding

/** Search result rows: the building number in large type, then the name. */
class BuildingAdapter(private val inflater: LayoutInflater) : BaseAdapter() {
    var items: List<Building> = emptyList()
        set(value) {
            field = value
            notifyDataSetChanged()
        }

    override fun getCount(): Int = items.size
    override fun getItem(position: Int): Building = items[position]
    override fun getItemId(position: Int): Long = position.toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val row = convertView?.let(ItemBuildingBinding::bind)
            ?: ItemBuildingBinding.inflate(inflater, parent, false)
        val building = items[position]
        row.buildingNumber.text = building.number.orEmpty()
        row.buildingName.text = building.name
        return row.root
    }
}

"""Extract and format table data for chart generation."""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from step2.slide_plan_models import ChartType
from .content_models import ChartData


@dataclass
class ParsedValue:
    """A parsed numeric value with metadata."""
    original: str
    numeric: float
    is_currency: bool
    is_percentage: bool
    unit: str = ""  # M, B, K, %, etc.


class ChartDataExtractor:
    """Extract chart-ready data from markdown tables."""
    
    def __init__(self):
        # Patterns for value parsing
        self.currency_pattern = re.compile(
            r'[$€£¥]\s*([\d,.]+)\s*([KMBT]?)',
            re.IGNORECASE
        )
        self.percentage_pattern = re.compile(
            r'([\d,.]+)\s*%'
        )
        self.number_pattern = re.compile(
            r'^-?[\d,.]+([KMBT%]?)',
            re.IGNORECASE
        )
    
    _GENERIC_SERIES_NAMES = {
        "value", "values", "value and units", "amount", "number",
        "data", "count", "total", "figure", "figures",
        "announced amount and units", "units",
    }

    def _clean_series_name(self, name: str, chart_title: str) -> str:
        """Replace generic series names with a meaningful label derived from chart title."""
        if name.strip().lower() in self._GENERIC_SERIES_NAMES:
            words = chart_title.split()
            if len(words) >= 2:
                return " ".join(words[:4])
            return chart_title or name
        return name

    def extract_chart_data(
        self,
        table_data: List[List[str]],
        chart_type: ChartType,
        table_index: int,
        chart_title: str,
        inventory_table_info: Optional[Dict] = None
    ) -> ChartData:
        """
        Extract chart data from a table.
        
        Args:
            table_data: 2D array of table cells
            chart_type: Desired chart type
            table_index: Index in document
            chart_title: Title for the chart
            inventory_table_info: Optional metadata from inventory
            
        Returns:
            ChartData object ready for Step 4
        """
        if not table_data or len(table_data) < 2:
            return self._create_error_chart_data(
                chart_type, table_index, chart_title,
                "Table has insufficient data"
            )
        
        headers = table_data[0] if table_data else []
        data_rows = table_data[1:] if len(table_data) > 1 else []
        
        if not data_rows:
            return self._create_error_chart_data(
                chart_type, table_index, chart_title,
                "No data rows found"
            )
        
        # Determine which columns are which
        category_col, numeric_cols = self._analyze_columns(
            headers, data_rows, inventory_table_info
        )
        
        # Extract categories
        categories = [
            row[category_col] if category_col < len(row) else f"Item {i}"
            for i, row in enumerate(data_rows)
        ]
        
        # Extract series
        series = []
        for col_idx in numeric_cols:
            if col_idx >= len(headers):
                continue
            
            series_name = headers[col_idx] if col_idx < len(headers) else f"Series {col_idx}"
            series_name = self._clean_series_name(series_name, chart_title)
            values = []
            
            for row in data_rows:
                if col_idx < len(row):
                    parsed = self._parse_value(row[col_idx])
                    values.append(parsed.numeric if parsed else 0.0)
                else:
                    values.append(0.0)
            
            series.append({
                "name": series_name,
                "values": values
            })
        
        # If no numeric columns found, treat first column as values
        if not series and len(headers) >= 2:
            values = []
            for row in data_rows:
                if len(row) > 1:
                    parsed = self._parse_value(row[1])
                    values.append(parsed.numeric if parsed else 0.0)
            
            if values:
                series.append({
                    "name": headers[1] if len(headers) > 1 else "Value",
                    "values": values
                })
        
        # Validate and adjust for chart type
        is_valid, errors = self._validate_chart_data(
            categories, series, chart_type
        )
        
        # Infer number format from values
        number_format = self._infer_number_format(table_data)
        
        return ChartData(
            chart_type=chart_type,
            title=chart_title,
            source_table_index=table_index,
            categories=categories,
            series=series,
            number_format=number_format,
            is_valid=is_valid,
            validation_errors=errors
        )
    
    def _analyze_columns(
        self,
        headers: List[str],
        data_rows: List[List[str]],
        inventory_table_info: Optional[Dict]
    ) -> Tuple[int, List[int]]:
        """
        Determine which column is categories and which are numeric.
        
        Returns:
            (category_column_index, list_of_numeric_column_indices)
        """
        if not headers:
            return 0, [1] if len(data_rows[0]) > 1 else []
        
        num_cols = len(headers)
        
        def column_values(col: int) -> List[str]:
            return [row[col] for row in data_rows if col < len(row)]

        def is_usable_category_col(col: int) -> bool:
            vals = [v for v in column_values(col) if v and v.strip()]
            if not vals:
                return False
            unique = {v.strip() for v in vals}
            if len(unique) < 2 and len(vals) > 1:
                return False  # degenerate: all rows share the same label
            avg_len = sum(len(v) for v in vals) / len(vals)
            if avg_len > 28:
                return False  # sentence-length labels make unreadable x-axis
            return True

        # Use inventory info if available
        if inventory_table_info:
            temporal_cols = inventory_table_info.get('temporal_columns', [])
            numeric_cols = inventory_table_info.get('numeric_columns', [])
            temporal_set = set(temporal_cols)

            series_cols = [c for c in numeric_cols if c not in temporal_set]

            for col in temporal_cols:
                if is_usable_category_col(col):
                    return col, series_cols

            non_numeric_cols = [
                i for i in range(num_cols)
                if i not in numeric_cols and i not in temporal_set
            ]
            for col in non_numeric_cols:
                if is_usable_category_col(col):
                    return col, series_cols or numeric_cols

            if series_cols or numeric_cols:
                category_candidates = [
                    i for i in range(num_cols) if i not in numeric_cols
                ]
                if category_candidates:
                    return category_candidates[0], series_cols or numeric_cols
        
        # Auto-detect from data
        numeric_cols = []
        category_candidates = []
        
        for col_idx in range(num_cols):
            # Sample values from this column
            sample_values = [
                row[col_idx] for row in data_rows[:5]
                if col_idx < len(row) and row[col_idx].strip()
            ]
            
            numeric_count = sum(1 for v in sample_values if self._is_numeric(v))
            total = len(sample_values) if sample_values else 1
            
            if numeric_count / total > 0.5:
                numeric_cols.append(col_idx)
            else:
                category_candidates.append(col_idx)
        
        # Pick category column
        if category_candidates:
            category_col = category_candidates[0]
        elif numeric_cols:
            # All numeric - use first as category (labels)
            category_col = numeric_cols[0]
            numeric_cols = numeric_cols[1:]
        else:
            category_col = 0
        
        return category_col, numeric_cols if numeric_cols else [1] if num_cols > 1 else []
    
    def _parse_value(self, value: str) -> Optional[ParsedValue]:
        """Parse a string value into numeric with metadata."""
        if not value or not value.strip():
            return None

        value = value.strip().replace(',', '')
        # Strip trailing unit word ("USD", "EUR", "ratio", "GW", "index points")
        # so "109,100,000,000.00 USD" or "22.09 ratio" parse cleanly.
        value = re.sub(r"\s+[A-Za-z][A-Za-z\s/\-]*$", "", value).strip()
        
        # Try currency
        currency_match = self.currency_pattern.match(value)
        if currency_match:
            number_part = currency_match.group(1).replace(',', '')
            suffix = currency_match.group(2).upper()
            try:
                num = float(number_part)
                multiplier = {'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}.get(suffix, 1)
                return ParsedValue(
                    original=value,
                    numeric=num * multiplier,
                    is_currency=True,
                    is_percentage=False,
                    unit=suffix
                )
            except ValueError:
                pass
        
        # Try percentage
        percent_match = self.percentage_pattern.match(value)
        if percent_match:
            try:
                num = float(percent_match.group(1))
                return ParsedValue(
                    original=value,
                    numeric=num,
                    is_currency=False,
                    is_percentage=True,
                    unit="%"
                )
            except ValueError:
                pass
        
        # Try plain number with suffix
        number_match = self.number_pattern.match(value)
        if number_match:
            number_part = number_match.group(0).replace(',', '')
            suffix = number_match.group(1).upper()
            
            # Remove suffix from number part
            for s in ['K', 'M', 'B', 'T', '%']:
                if number_part.upper().endswith(s):
                    number_part = number_part[:-1]
                    suffix = s
                    break
            
            try:
                num = float(number_part)
                multiplier = {'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}.get(suffix, 1)
                is_percent = suffix == '%'
                
                return ParsedValue(
                    original=value,
                    numeric=num if is_percent else num * multiplier,
                    is_currency=False,
                    is_percentage=is_percent,
                    unit=suffix
                )
            except ValueError:
                pass
        
        return None
    
    def _is_numeric(self, value: str) -> bool:
        """Check if a value is numeric."""
        return self._parse_value(value) is not None
    
    def _validate_chart_data(
        self,
        categories: List[str],
        series: List[Dict[str, Any]],
        chart_type: ChartType
    ) -> Tuple[bool, List[str]]:
        """Validate data is suitable for the chart type."""
        errors = []
        is_valid = True
        
        # Common validations
        if len(categories) == 0:
            errors.append("No categories found")
            is_valid = False
        
        if len(series) == 0:
            errors.append("No data series found")
            is_valid = False
        
        # Chart type specific validations
        if chart_type == ChartType.PIE:
            # Pie should have single series
            if len(series) > 1:
                errors.append("Pie chart should have only one series, using first")
                series = [series[0]]
            
            # Check for negative values
            if series and any(v < 0 for v in series[0].get('values', [])):
                errors.append("Pie chart has negative values")
                is_valid = False
            
            # Pie works best with < 8 categories
            if len(categories) > 8:
                errors.append(f"Pie chart has {len(categories)} categories (max 8 recommended)")
        
        elif chart_type == ChartType.LINE:
            # Line needs at least 2 data points
            if len(categories) < 2:
                errors.append("Line chart needs at least 2 data points")
                is_valid = False
        
        elif chart_type in [ChartType.BAR, ChartType.HORIZONTAL_BAR]:
            # Bar charts get crowded with too many categories
            if len(categories) > 15:
                errors.append(f"Bar chart has {len(categories)} categories (may be crowded)")
        
        return is_valid, errors
    
    def _infer_number_format(self, table_data: List[List[str]]) -> str:
        """Infer the appropriate number format from table values."""
        if not table_data or len(table_data) < 2:
            return "General"
        
        # Sample values from data rows
        sample_values = []
        for row in table_data[1:]:  # Skip header
            for cell in row[1:]:  # Skip first column (usually categories)
                if cell.strip():
                    sample_values.append(cell)
                    if len(sample_values) >= 10:
                        break
            if len(sample_values) >= 10:
                break
        
        # Check patterns
        currency_count = 0
        percent_count = 0
        
        for val in sample_values:
            parsed = self._parse_value(val)
            if parsed:
                if parsed.is_currency:
                    currency_count += 1
                elif parsed.is_percentage:
                    percent_count += 1
        
        total = len(sample_values) if sample_values else 1
        
        if currency_count / total > 0.5:
            return "$#,##0.0"
        elif percent_count / total > 0.5:
            return "0.0%"
        else:
            return "#,##0.0"
    
    def _create_error_chart_data(
        self,
        chart_type: ChartType,
        table_index: int,
        title: str,
        error: str
    ) -> ChartData:
        """Create a placeholder chart data when extraction fails."""
        return ChartData(
            chart_type=chart_type,
            title=f"{title} (Error)",
            source_table_index=table_index,
            categories=["Error"],
            series=[{"name": "Data", "values": [0]}],
            is_valid=False,
            validation_errors=[error]
        )
    
    def suggest_chart_type(self, table_data: List[List[str]]) -> ChartType:
        """Suggest the best chart type for this table."""
        if not table_data or len(table_data) < 2:
            return ChartType.BAR
        
        headers = table_data[0]
        data_rows = table_data[1:]
        
        # Analyze columns
        _, numeric_cols = self._analyze_columns(headers, data_rows, None)
        
        # Single series -> Bar or Pie
        if len(numeric_cols) == 1:
            # Check if categories are years/temporal
            first_col_values = [row[0] for row in data_rows if row]
            temporal_pattern = re.compile(r'^(20\d{2}|19\d{2}|Q[1-4]|\d{4}-\d{2})$')
            temporal_count = sum(1 for v in first_col_values if temporal_pattern.match(str(v)))
            
            if temporal_count / len(first_col_values) > 0.5:
                return ChartType.LINE
            
            # Few categories -> Pie
            if len(data_rows) <= 6:
                return ChartType.PIE
            
            return ChartType.BAR
        
        # Multiple series -> Grouped bar or line
        if len(numeric_cols) > 1:
            # Check for temporal x-axis
            first_col_values = [row[0] for row in data_rows if row]
            temporal_pattern = re.compile(r'^(20\d{2}|19\d{2}|Q[1-4])$')
            temporal_count = sum(1 for v in first_col_values if temporal_pattern.match(str(v)))
            
            if temporal_count / len(first_col_values) > 0.5:
                return ChartType.LINE
            
            return ChartType.GROUPED_BAR
        
        return ChartType.BAR

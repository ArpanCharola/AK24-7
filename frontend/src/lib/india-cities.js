// Single source of truth for India city/location pickers.
export const INDIA_CITIES = [
  "Agra", "Ahmedabad", "Anand", "Aurangabad", "Bangalore", "Bengaluru",
  "Bareilly", "Belagavi", "Bhavnagar", "Bhilai", "Bhopal", "Bhubaneswar",
  "Chandigarh", "Chennai", "Coimbatore", "Cuttack", "Dehradun", "Delhi",
  "Dhanbad", "Durgapur", "Faridabad", "Gandhinagar", "Ghaziabad", "Goa",
  "Gorakhpur", "Greater Noida", "Gurgaon", "Gurugram", "Guwahati", "Gwalior",
  "Hubballi", "Hyderabad", "Indore", "Jabalpur", "Jaipur", "Jalandhar",
  "Jamnagar", "Jamshedpur", "Jodhpur", "Kanpur", "Kochi", "Kolhapur",
  "Kolkata", "Kota", "Kozhikode", "Lucknow", "Ludhiana", "Madurai",
  "Mangaluru", "Meerut", "Mohali", "Mumbai", "Mysuru", "Nagpur", "Nashik",
  "Navi Mumbai", "New Delhi", "Noida", "Panipat", "Patna", "Prayagraj",
  "Pune", "Raipur", "Rajkot", "Ranchi", "Salem", "Solapur", "Surat",
  "Thane", "Thiruvananthapuram", "Tiruchirappalli", "Udaipur", "Vadodara",
  "Vapi", "Varanasi", "Vellore", "Visakhapatnam", "Vijayawada", "Warangal",
];

export const INDIA_LOCATION_OPTIONS = [
  "Remote India",
  "Pan India",
  ...INDIA_CITIES,
];

export const WORK_MODE_FILTERS = [
  { label: "All work modes", value: "" },
  { label: "Remote", value: "remote" },
  { label: "Hybrid", value: "hybrid" },
  { label: "On-site", value: "onsite" },
];

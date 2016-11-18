package c2corg

import io.gatling.core.Predef._

object C2corgConf {
  val num_users = 10
  val ramp_time_seconds = 10

  val ui_url = "http://www.demov6.camptocamp.org"
  val api_url = "http://api.demov6.camptocamp.org"
  val forum_url = "http://forum.demov6.camptocamp.org"
  val image_url = "http://images.demov6.camptocamp.org"

  val header_json = Map(
      "Accept" -> "application/json",
      "Origin" -> ui_url)

  val header_html = Map("Accept" -> "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

  val header_discourse_1 = Map(
    "Discourse-Track-View" -> "true",
    "X-CSRF-Token" -> "undefined",
    "X-Requested-With" -> "XMLHttpRequest")

  val header_discourse_2 = Map(
    "X-CSRF-Token" -> "undefined",
    "X-Requested-With" -> "XMLHttpRequest")

  val basic_auth_username = "c2corg"
  val basic_auth_password = "c2corg"

  val black_list = BlackList("""http://server1.affiz.net/.*""", """https://www.google-analytics.com/analytics.js""", """https://www.google.com/recaptcha/api.js?.*""", """http://sos.exo.io/.*""", """.*/static/.*""", """.*/images/proxy/.*""", """http://i.imgur.com/.*""", """.*.ico""", """.*css.*""", """.*.js""")
}

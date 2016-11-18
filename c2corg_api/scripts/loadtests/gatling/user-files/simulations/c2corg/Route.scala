package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Route {
  val feeder = csv("routes.csv").random

  val view = feed(feeder).exec(
    http("View route")
      .get("/routes/${id}/${lang}/foo")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}

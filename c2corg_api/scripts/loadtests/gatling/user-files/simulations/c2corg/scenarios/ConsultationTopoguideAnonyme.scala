package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._


class ConsultationTopoguideAnonyme extends Simulation {

	val httpProtocol = http
		.baseURL(C2corgConf.ui_url)
		.inferHtmlResources(C2corgConf.black_list, WhiteList())
		.acceptHeader("*/*")
		.acceptEncodingHeader("gzip, deflate")
		.acceptLanguageHeader("fr-CH,en-US;q=0.7,en;q=0.3")
		.userAgentHeader("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:49.0) Gecko/20100101 Firefox/49.0")

	val scn = scenario("ConsultationTopoguideAnonyme")
                .exec(Homepage.init)
                .pause(8)
                .exec(Homepage.browse)
		.pause(6)
		.exec(Outing.view)
		.pause(14)
                .exec(Route.view)
		.pause(10)
		.exec(Waypoint.view)

	setUp(scn.inject(atOnceUsers(1))).protocols(httpProtocol)
}
